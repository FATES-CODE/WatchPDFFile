import os
import re
import time
from traceback import format_exc
from watchfiles import watch
from pdf2image import convert_from_path
from google.cloud import vision  
import io
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"C:\Users\FATES\Desktop\keys\google-vision-key.json"

WATCH_DIR = r"C:\Users\FATES\Desktop\SCAN"
POPPLER_PATH = r"C:\poppler\Library\bin"
#환경변수 설정
client = vision.ImageAnnotatorClient()

BL_CORRECTION_DICTIONARY = [
    ["TIMBHLJ", "TIMBHIJ"],  
    ["HLJ", "HIJ"],
    ["XOK", "YOK"],
    ["2600106", "2606106"],  
    ["YOK2600", "YOK2606"]
]

def fix_bl_o_and_zero(text):
    clean_text = re.sub(r"[^A-Z0-9]", "", text.upper())
    clean_text = clean_text.replace("REF", "")
    
    for wrong, right in BL_CORRECTION_DICTIONARY:
        if wrong in clean_text:
            clean_text = clean_text.replace(wrong, right)
            
    match_digit = re.search(r"\d", clean_text)
    if match_digit:
        digit_index = match_digit.start()
        prefix = clean_text[:digit_index].replace("0", "O")
        suffix = clean_text[digit_index:].replace("O", "0")
        return prefix + suffix
    if len(clean_text) > 4:
        prefix = clean_text[:4].replace("0", "O")
        suffix = clean_text[4:].replace("O", "0")
        return prefix + suffix

    return clean_text

def log(message, level="INFO"):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")

def parse_bl_from_text(full_text):
    """
    Vision API가 추출한 전체 텍스트에서 프롬프트에 있던 조건들을 
    정규표현식과 규칙 기반으로 필터링하는 함수
    """
    lines = [line.strip() for line in full_text.split('\n') if line.strip()]
    
    for line in lines:
        clean_line = line.replace(" ", "")
        fts_match = re.search(r'FTS[A-Z0-9]+', clean_line, re.IGNORECASE)
        if fts_match:
            extracted = fts_match.group(0).upper()
            if len(extracted) >= 6:
                prefix = extracted[:3]      # FTS
                middle = extracted[3:6].replace("0", "O")  # TY0 -> TYO
                suffix = extracted[6:]
                extracted = prefix + middle + suffix
            
            return extracted

    for line in lines:
        if any(keyword in line.upper() for keyword in ["HB/L", "H B/L", "B/L"]):
            bl_match = re.search(r'[A-Z0-9]+[-,\sA-Z0-9]+', line.upper())
            if bl_match:
                found = bl_match.group(0)
                for kw in ["H B/L", "HB/L", "B/L"]:
                    found = found.replace(kw, "")
                found = found.strip(" :-,")
                if found:
                    return found

    return lines[0] if lines else ""

def ocr_with_vision_api(pdf_page_image):
    """
    Google Cloud Vision API를 사용하여 이미지에서 텍스트를 추출합니다.
    """
    img_byte_arr = io.BytesIO()
    pdf_page_image.save(img_byte_arr, format='JPEG')
    img_bytes = img_byte_arr.getvalue()

    image = vision.Image(content=img_bytes)

    for attempt in range(3):
        try:
            time.sleep(2) 
            response = client.text_detection(image=image)
            annotations = response.text_annotations
            
            if response.error.message:
                raise Exception(response.error.message)
                
            if not annotations:
                return ""
                
            full_text = annotations[0].description
            
            detected_number = parse_bl_from_text(full_text)
            return detected_number

        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "QUOTA" in error_msg.upper():
                wait_time = (attempt + 1) * 10
                log(f"상세에러: {error_msg}", "WARNING")
                log(f"{wait_time}초 후 재시도({attempt+1}/3)", "WARNING")
                time.sleep(wait_time)
            else:
                log(f"구글 Vision API 호출 중 에러 발생: {error_msg}", "ERROR")
                raise e
                
    return ""

def process_pdf(file_path):
    if not os.path.exists(file_path):
        return

    original_name = os.path.basename(file_path)
    if any(ext in original_name.lower() for ext in [".tmp", ".crdownload", ".download"]):
        return

    log(f"PDF 감지: {original_name}")
    time.sleep(5)

    log(f"스캔본 PDF 분석 시작  {original_name}")

    try:
        pages = convert_from_path(file_path, first_page=1, last_page=1, poppler_path=POPPLER_PATH)
        if not pages:
            log("PDF를 이미지로 변환하는 데 실패.", "ERROR")
            return

        # 수정된 Vision API 함수 호출
        raw_text = ocr_with_vision_api(pages[0])
        log(f"Vision API 추출 결과: {raw_text}")

        if not raw_text:
            log("Vision API가 문서 ", "WARNING")
            detected_bl = os.path.splitext(original_name)[0].upper().strip()
        else:
            is_fts = "FTS" in raw_text.upper() or "FTS" in original_name.upper()
            cleaned_number = fix_bl_o_and_zero(raw_text)
            
            if is_fts:
                if not cleaned_number.startswith("FTS"):
                    detected_bl = f"FTS{cleaned_number}"
                else:
                    detected_bl = cleaned_number
            else:
                detected_bl = cleaned_number
                
            log(f"최종 확정된 B/L 번호: {detected_bl}", "SUCCESS")

        if detected_bl:
            target_name = f"{detected_bl}.pdf"
            target_path = os.path.join(WATCH_DIR, target_name)

            if original_name.upper() == target_name.upper():
                log("파일 변경 완료 (이미 일치함)")
                return

            if os.path.exists(target_path):
                timestamp = time.strftime("%H%M%S")
                target_path = os.path.join(WATCH_DIR, f"{detected_bl}_{timestamp}.pdf")

            os.rename(file_path, target_path)
            log(f"{original_name} -> {os.path.basename(target_path)}", "SUCCESS")

    except Exception as e:
        log(f"파일 처리 중 오류 발생: {str(e)}", "ERROR")
        print(format_exc())

def start_watching():
    log(f"스캔 모니터링 시작: {WATCH_DIR}")
    for changes in watch(WATCH_DIR):
        for change_type, file_path in changes:
            if change_type.value == 1 and file_path.lower().endswith(".pdf"):
                process_pdf(file_path)
def main():
    print("PDF 감시 프로그램을 시작")
if __name__ == "__main__":
    start_watching()