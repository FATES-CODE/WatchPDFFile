WatchPDFFile.py 스크립트는 지정된 디렉토리(WATCH_DIR)에서 새로운 PDF 파일을 감지하고, 해당 파일에서 House B/L (HBL), HAWB, 또는 REF 번호를 추출하여 파일을 적절하게 이름을 변경하는 자동화된 솔루션을 제공합니다. 
Key Components
Directory Monitoring: watchfiles 라이브러리를 사용하여 WATCH_DIR 디렉토리에서 PDF 파일의 생성 또는 수정을 감지합니다.
File Processing: 감지된 PDF 파일을 처리하여 번호를 추출하고 파일을 이름을 변경합니다.
Text Extraction: Google Cloud Vision API를 사용하여 PDF 파일의 첫 페이지에서 텍스트를 추출합니다.
Text Parsing: 추출된 텍스트에서 HBL, HAWB, 또는 REF 번호를 추출합니다.
File Renaming: 추출된 번호를 기반으로 파일을 이름을 변경하고, 필요할 경우 타임스탬프를 추가하여 중복을 방지합니다.
Error Handling: 다양한 오류 상황을 처리하여 스크립트의 안정성을 보장합니다.
Detailed Function Descriptions
start_watching()
Description: WATCH_DIR 디렉토리에서 PDF 파일의 생성 또는 수정을 감지하고, 각 파일을 process_pdf 함수로 처리합니다.
Parameters: None
Return Value: None
Process:
WATCH_DIR 디렉토리에서 PDF 파일의 생성 또는 수정을 감지합니다.
감지된 파일 경로를 process_pdf 함수로 전달합니다.
process_pdf(file_path)
Description: 주어진 PDF 파일에서 HBL, HAWB, 또는 REF 번호를 추출하고 파일을 적절하게 이름을 변경합니다.
Parameters:
file_path: 처리할 PDF 파일의 경로 (문자열)
Return Value: None
Process:
파일이 존재하는지 확인합니다.
파일 이름이 무시 목록에 있는지 확인합니다.
파일의 SHA-256 해시를 계산하여 캐싱된 파일인지 확인합니다.
파일이 처음 처리되는 경우, OCR을 통해 텍스트를 추출합니다.
추출된 텍스트에서 HBL, HAWB, 또는 REF 번호를 추출합니다.
추출된 번호를 기반으로 파일을 이름을 변경합니다. 필요할 경우 타임스탬프를 추가하여 중복을 방지합니다.
파일이 이미 존재하고 동일한 내용인 경우, 원본 파일을 삭제합니다.
ocr_with_vision_api(pdf_page_image)
Description: Google Cloud Vision API를 사용하여 PDF 페이지 이미지에서 텍스트를 추출합니다.
Parameters:
pdf_page_image: OCR을 수행할 PDF 페이지 이미지 (PIL 이미지 객체)
Return Value: 추출된 텍스트 (문자열)
Process:
PDF 페이지 이미지를 JPEG 형식으로 변환합니다.
Google Cloud Vision API를 사용하여 텍스트를 추출합니다.
추출된 텍스트에서 HBL, HAWB, 또는 REF 번호를 근거로 한 주변 텍스트를 추출합니다.
주변 텍스트에서 번호를 추출하고 반환합니다.
extract_bl_by_regex(text)
Description: 정규 표현식을 사용하여 텍스트에서 HBL, HAWB, 또는 REF 번호를 추출합니다.
Parameters:
text: 추출할 텍스트 (문자열)
Return Value: 추출된 번호 (문자열)
Process:
텍스트를 대문자로 변환하고, 특정 패턴을 사용하여 번호를 검색합니다.
검색된 번호를 반환합니다. 만약 검색된 번호가 없으면 빈 문자열을 반환합니다.
extract_hbl_from_anchor_line(line_text)
Description: 주어진 라인 텍스트에서 HBL, HAWB, 또는 REF 번호를 추출합니다.
Parameters:
line_text: 번호를 추출할 라인 텍스트 (문자열)
Return Value: 추출된 번호 (문자열)
Process:
라인 텍스트를 대문자로 변환하고, 특정 패턴을 사용하여 번호를 검색합니다.
검색된 번호를 반환합니다. 만약 검색된 번호가 없으면 None을 반환합니다.
parse_bl_from_text_with_local_ai(target_text)
Description: 로컬 AI 모델을 사용하여 텍스트에서 HBL, HAWB, 또는 REF 번호를 추출합니다.
Parameters:
target_text: 추출할 텍스트 (문자열)
Return Value: 추출된 번호 (문자열)
Process:
로컬 AI 모델에게 텍스트를 제공하여 번호를 추출합니다.
추출된 번호를 반환합니다. 만약 검색된 번호가 없으면 빈 문자열을 반환합니다.
fix_bl_o_and_zero(text)
Description: 텍스트에서 "O"와 "0"을 적절히 교환하여 번호를 정규화합니다.
Parameters:
text: 정규화할 텍스트 (문자열)
Return Value: 정규화된 텍스트 (문자열)
Process:
텍스트에서 "O"와 "0"을 교환하여 번호를 정규화합니다.
정규화된 텍스트를 반환합니다.
calculate_file_hash(file_path)
Description: 주어진 파일의 SHA-256 해시를 계산합니다.
Parameters:
file_path: 해시를 계산할 파일의 경로 (문자열)
Return Value: 파일의 SHA-256 해시 (문자열)
Process:
파일이 존재하는지 확인합니다.
파일의 내용을 읽어 SHA-256 해시를 계산합니다.
계산된 해시를 반환합니다.
log(message, level="INFO")
Description: 메시지를 로그로 출력합니다.
Parameters:
message: 로그로 출력할 메시지 (문자열)
level: 로그 레벨 (기본값: “INFO”) (문자열)
Return Value: None
Process:
현재 시간을 기록합니다.
메시지를 지정된 로그 레벨과 함께 출력합니다.
Usage
Directory Configuration: WATCH_DIR 변수를 감시할 디렉토리 경로로 설정합니다.
Poppler Path Configuration: POPPLER_PATH 변수를 Poppler 유틸리티가 설치된 경로로 설정합니다.
Google Cloud Vision API Credentials: GOOGLE_APPLICATION_CREDENTIALS 환경 변수를 Google Cloud Vision API 자격 증명 파일의 경로로 설정합니다.
Run Script: 스크립트를 실행합니다.
Example
python
if __name__ == "__main__":
    start_watching()
이 코드 스니펫은 스크립트가 직접 실행될 때 start_watching 함수를 호출합니다. 
Conclusion
WatchPDFFile.py 스크립트는 지정된 디렉토리에서 PDF 파일을 감지하고, 파일 내용에서 HBL, HAWB, 또는 REF 번호를 추출하여 파일을 이름을 변경합니다. 이 과정에서 캐싱과 오류 처리를 통해 효율적이고 정확한 파일 처리를 보장합니다.
