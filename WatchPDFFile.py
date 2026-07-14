import os
import re
import time
import hashlib
from traceback import format_exc
from watchfiles import watch
from pdf2image import convert_from_path
from google.cloud import vision 
import ollama
import io

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = r"C:\Users\FATES\Desktop\folder\cloud-visionAPI.json"

WATCH_DIR = r"C:\Users\FATES\Desktop\SCAN"
POPPLER_PATH = r"C:\poppler\Library\bin"

client_vision = vision.ImageAnnotatorClient()
processed_files = {}
ignore_files = set()
processed_hashes = {} # file_hash -> detected_bl 캐싱

BL_CORRECTION_DICTIONARY = [
    ["TIMBHLJ", "TIMBHIJ"],  
    ["HLJ", "HIJ"],
    ["XOK", "YOK"],
    ["2600106", "2606106"],  
    ["YOK2600", "YOK2606"]
]

def calculate_file_hash(file_path):
    hash_sha256 = hashlib.sha256()
    try:
        if not os.path.exists(file_path):
            return None
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    except Exception as e:
        log(f"Error calculating hash for {os.path.basename(file_path)}: {str(e)}", "WARNING")
        return None

def fix_bl_o_and_zero(text):
    # 하이픈(-)을 보존하도록 정규식 수정
    clean_text = re.sub(r"[^A-Z0-9\-]", "", text.upper())
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

def group_words_into_lines(words):
    words_sorted = sorted(words, key=lambda w: min(v.y for v in w.bounding_poly.vertices))
    
    lines = []
    for word in words_sorted:
        box = word.bounding_poly.vertices
        y_min = min(v.y for v in box)
        y_max = max(v.y for v in box)
        y_center = (y_min + y_max) / 2
        
        placed = False
        for line in lines:
            line_y_center = sum((min(v.y for v in w.bounding_poly.vertices) + max(v.y for v in w.bounding_poly.vertices))/2 for w in line) / len(line)
            if abs(y_center - line_y_center) < 15:
                line.append(word)
                placed = True
                break
        if not placed:
            lines.append([word])
            
    for line in lines:
        line.sort(key=lambda w: min(v.x for v in w.bounding_poly.vertices))
        
    lines.sort(key=lambda line: sum((min(v.y for v in w.bounding_poly.vertices) + max(v.y for v in w.bounding_poly.vertices))/2 for w in line) / len(line))
    
    return lines

def extract_text_near_anchor_by_lines(response):
    annotations = response.text_annotations
    if len(annotations) <= 1:
        return ""

    words = annotations[1:]
    lines = group_words_into_lines(words)
    
    hbl_line_idx = -1
    hbl_patterns = [
        r"H\s*B\s*/?\s*L", 
        r"HBL", 
        r"HAWB", 
        r"HOUSE\s*B\s*/?\s*L", 
        r"HOUSE\s*BL"
    ]
    
    for idx, line in enumerate(lines):
        line_text = " ".join(w.description for w in line).upper()
        if any(re.search(p, line_text) for p in hbl_patterns):
            hbl_line_idx = idx
            break
            
    if hbl_line_idx == -1:
        for idx, line in enumerate(lines):
            line_text = " ".join(w.description for w in line).upper()
            if re.search(r"REF", line_text):
                hbl_line_idx = idx
                break
            elif re.search(r"B\s*/?\s*L", line_text):
                if not (re.search(r"M\s*B\s*/?\s*L", line_text) or re.search(r"MBL", line_text) or re.search(r"MASTER", line_text)):
                    hbl_line_idx = idx
                    break

    if hbl_line_idx == -1:
        log("THERE'S NO BLNUMBER", "WARNING")
        return ""

    context_lines = []
    for offset in range(3):
        target_idx = hbl_line_idx + offset
        if target_idx < len(lines):
            line_text = " ".join(w.description for w in lines[target_idx])
            context_lines.append(line_text)
            
    combined_text = "\n".join(context_lines)
    log(f"OCR text:\n{combined_text}")
    return combined_text

def extract_bl_by_regex(text):
    text_upper = text.upper()
    # 하이픈(-) 매칭 추가 및 최소 접두사 길이 2로 수정 (예: TPL-12763 매칭)
    match = re.search(r"\b([A-Z]{2,8}[\s\-/]*[0-9]{4,12}[A-Z0-9\-]*)\b", text_upper)
    if match:
        val = re.sub(r"\s", "", match.group(1))
        log(f"COMPLETE PARSER {val}", "SUCCESS")
        return val
    match_num = re.search(r"\b([0-9]{10,14})\b", text_upper)
    if match_num:
        val = match_num.group(1)
        log(f"COMPLETE PARSER THE NUMBER: {val}", "SUCCESS")
        return val
        
    match_alpha = re.search(r"\b([A-Z]{7,12})\b", text_upper)
    if match_alpha:
        val = match_alpha.group(1)
        if val not in ["PAYMENT", "INVOICE", "SHIPPER", "NOTIFY", "ARRIVAL", "TERMS"]:
            log(f"COMPLETE THE ENGLISH NUMBER: {val}", "SUCCESS")
            return val
            
    return ""

def extract_hbl_from_anchor_line(line_text):
    line_upper = line_text.upper()
    
    hbl_label_patterns = [
        r"H\s*B\s*/?\s*L",
        r"HBL",
        r"HAWB",
        r"HOUSE\s*B\s*/?\s*L",
        r"HOUSE\s*BL",
        r"REF\s*NO",
        r"REF"
    ]
    
    label_pos = -1
    for pattern in hbl_label_patterns:
        match = re.search(pattern, line_upper)
        if match:
            label_pos = match.end()
            break
            
    if label_pos == -1:
        return None
        
    text_after_label = line_upper[label_pos:]
    text_after_label = re.sub(r"^[^A-Z0-9]+", "", text_after_label)
    
    match_code = re.search(r"\b([A-Z]{2,8}[\s\-/]*[0-9]{4,12}[A-Z0-9\-]*|[0-9]{8,15})\b", text_after_label)
    if match_code:
        code = re.sub(r"\s+", "", match_code.group(1))
        return code
        
    words = re.findall(r"\b[A-Z0-9\-]{4,20}\b", text_after_label)
    if words:
        return words[0]
        
    return None

def parse_bl_from_text_with_local_ai(target_text):
    if not target_text:
        return ""

    system_prompt = """You are a logistics data extraction specialist.
Your task is to extract ONLY the single correct House B/L (or HAWB, REF) number code from the provided text snippet.

CRITICAL RULES:
1. Output ONLY the single House B/L, HAWB, or REF number.
2. NEVER output both House B/L (HBL) and Master B/L (MBL).
3. If both House B/L and Master B/L are present, output ONLY the House B/L number. Do NOT extract the Master B/L number (often ends in 'MB' or similar).
4. Always prioritize HBL/H B/L/HAWB over MBL/M B/L and REF.
5. Do not output labels, markdown code blocks, prefixes, explanations, punctuation, or greetings.
6. Merge any spaces within the code itself (e.g., 'FOI 2606 147' -> 'FOI2606147'). Keep hyphens if they are part of the code (e.g., 'TPL-12763' -> 'TPL-12763').
7. If no valid code is found, output an empty string.

Examples:
- Input:
H B / L NO PUSOSA26070008
Notify Party
M B / L NO PUSOSA26070008MB
-> Output: PUSOSA26070008

- Input:
HB / L NO ATNL2607010
Notify Party M B / L NO PKFCBS260709212
SAME AS CONSIGNEE
-> Output: ATNL2607010

- Input: 'HBL STS2606012 MBL FBTYO260568 REF . FOI 2606105' -> Output: STS2606012
- Input: 'HBL 550141772761 MBL 2606JP00609 REF . FOI 2606240' -> Output: 550141772761
- Input: 'HBL WDKHKT26050001 MBL PUSHKT26050023' -> Output: WDKHKT26050001
- Input: 'H B/L NO : SMRL260606BUOSA M B/L NO : ESSASEL26060473' -> Output: SMRL260606BUOSA
- Input: 'REF . FOI 2606147 ● AGENT PAYMENT' -> Output: FOI2606147"""

    user_prompt = f"Text Snippet:\n{target_text}"

    try:
        response = ollama.chat(
            model='qwen2.5:1.5b',
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            options={
                'temperature': 0.1 
            }
        )
        raw_response = response['message']['content']
        log(f"response: '{raw_response}'")
        
        detected_bl = raw_response.strip()
        
        code_block_match = re.search(r"```(?:[a-zA-Z0-9-]*)\s*(.*?)\s*```", detected_bl, re.DOTALL)
        if code_block_match:
            detected_bl = code_block_match.group(1).strip()
            
        if ":" in detected_bl:
            parts = detected_bl.split(":", 1)
            if len(parts[1].strip()) >= 4:
                detected_bl = parts[1].strip()
        elif "=" in detected_bl:
            parts = detected_bl.split("=", 1)
            if len(parts[1].strip()) >= 4:
                detected_bl = parts[1].strip()
                
        words = re.split(r"\s+", detected_bl)
        ignore_words = {"HBL", "MBL", "HAWB", "REF", "NO", "HOUSE", "MASTER", "B/L", "BL", "NUMBER", "CODE"}
        
        cleaned_words = []
        for w in words:
            # 하이픈(-)을 제거하지 않도록 정규식 수정
            w_clean = re.sub(r"^[^A-Z0-9\-]+|[^A-Z0-9\-]+$", "", w.upper())
            if w_clean and w_clean not in ignore_words and len(w_clean) >= 4:
                cleaned_words.append(w_clean)
        
        if len(cleaned_words) > 1:
            hbl_candidates = [c for c in cleaned_words if not c.endswith("MB")]
            if hbl_candidates:
                detected_bl = hbl_candidates[0]
            else:
                detected_bl = cleaned_words[0]
        elif cleaned_words:
            detected_bl = cleaned_words[0]
        else:
            detected_bl = ""
        
        if re.search(r"[\uac00-\ud7a3\u3131-\u318e]", detected_bl):
            log("filtering korean.", "WARNING")
            return ""
            
        return detected_bl
    except Exception as e:
        log(f"error: {str(e)}", "ERROR")
        return ""

def ocr_with_vision_api(pdf_page_image):
    img_byte_arr = io.BytesIO()
    pdf_page_image.save(img_byte_arr, format='JPEG')
    img_bytes = img_byte_arr.getvalue()

    image = vision.Image(content=img_bytes)

    for attempt in range(3):
        try:
            time.sleep(2) 
            response = client_vision.document_text_detection(image=image)
            
            if response.error.message:
                raise Exception(response.error.message)
                
            if not response.text_annotations:
                return ""
                
            near_text = extract_text_near_anchor_by_lines(response)
            
            if not near_text:
                near_text = response.text_annotations[0].description
                
            detected_number = ""
            
            if near_text:
                first_line = near_text.split("\n")[0]
                detected_number = extract_hbl_from_anchor_line(first_line)
                if detected_number:
                    log(f"Deterministic parser result: {detected_number}", "SUCCESS")
                    return detected_number
            
            if not detected_number:
                detected_number = parse_bl_from_text_with_local_ai(near_text)
            
            if not detected_number:
                log("no result", "INFO")
                detected_number = extract_bl_by_regex(near_text)
                
            return detected_number

        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg or "QUOTA" in error_msg.upper():
                wait_time = (attempt + 1) * 10
                time.sleep(wait_time)
            else:
                log(f"error in Vision API: {error_msg}", "ERROR")
                raise e
                
    return ""

def process_pdf(file_path):
    if not os.path.exists(file_path):
        return

    file_name = os.path.basename(file_path)
    
    if file_name in ignore_files:
        return

    file_hash = calculate_file_hash(file_path)
    if not file_hash:
        return

    if file_hash in processed_hashes:
        detected_bl = processed_hashes[file_hash]
        log(f"File {file_name} already processed (Cache hit). BL: {detected_bl}")
    else:
        current_time = time.time()
        if file_name in processed_files:
            if current_time - processed_files[file_name] < 5:
                return
                
        processed_files[file_name] = current_time

        if any(ext in file_name.lower() for ext in [".tmp", ".crdownload", ".download"]):
            return

        log(f"PDF: {file_name}")
        
        time.sleep(8) 

        try: 
            pages = convert_from_path(file_path, first_page=1, last_page=1, poppler_path=POPPLER_PATH)
            if not pages:
                log("error in folderdestination", "ERROR")
                return

            raw_text = ocr_with_vision_api(pages[0])
            log(f"AIs result: {raw_text}")

            if not raw_text or len(raw_text) < 4:
                log("there's not bl number", "WARNING")
                detected_bl = os.path.splitext(file_name)[0].upper().strip()
            else:
                is_fts = "FTS" in raw_text.upper() or "FTS" in file_name.upper()
                cleaned_number = fix_bl_o_and_zero(raw_text)
                
                if not cleaned_number or len(cleaned_number) < 4:
                    log("THE LENGTH SHORT", "WARNING")
                    detected_bl = os.path.splitext(file_name)[0].upper().strip()
                else:
                    if is_fts:
                        if not cleaned_number.startswith("FTS"):
                            detected_bl = f"FTS{cleaned_number}"
                        else:
                            detected_bl = cleaned_number
                    else:
                        detected_bl = cleaned_number
                        
                    log(f"BL NUMBER: {detected_bl}", "SUCCESS")
            
            processed_hashes[file_hash] = detected_bl

        except Exception as e:
            log(f"ERROR: {str(e)}", "ERROR")
            print(format_exc())
            return

    if detected_bl:
        target_name = f"{detected_bl}.pdf"
        target_path = os.path.join(WATCH_DIR, target_name)

        if file_name.upper() == target_name.upper():
            log(f"COMPLETE CHANING THE FILE NAME: {file_name}")
            return

        if os.path.exists(target_path):
            target_hash = calculate_file_hash(target_path)
            if target_hash == file_hash:
                log(f"Target file already exists and is identical. Deleting restored duplicate {file_name}.", "INFO")
                try:
                    if os.path.exists(file_path):
                        with open(file_path, "wb") as f:
                            f.truncate(0)
                        time.sleep(1)
                        os.remove(file_path)
                except Exception as delete_error:
                    log(f"Failed to delete duplicate source: {str(delete_error)}", "WARNING")
                return
            else:
                timestamp = time.strftime("%H%M%S")
                target_name = f"{detected_bl}_{timestamp}.pdf"
                target_path = os.path.join(WATCH_DIR, target_name)

        ignore_files.add(target_name)
        ignore_files.add(file_name)
        
        try:
            os.rename(file_path, target_path)
            log(f"{file_name} -> {os.path.basename(target_path)} (완료)", "SUCCESS")
        except Exception as rename_error:
            log(f"Rename failed: {str(rename_error)}", "ERROR")

def start_watching():
    log(f"SCAN START: {WATCH_DIR}")
    for changes in watch(WATCH_DIR):
        for change_type, file_path in changes:
            if change_type.value in [1, 2] and file_path.lower().endswith(".pdf"):
                process_pdf(file_path)

if __name__ == "__main__":
    start_watching()