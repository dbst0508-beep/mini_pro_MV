from transformers import AutoImageProcessor, AutoModelForObjectDetection  # ①탐지 모델 불러오는 클래스들
from transformers import CLIPModel, CLIPProcessor  # ②세부 라벨링(FashionCLIP) 불러오는 클래스들

DETECTION_MODEL_NAME = "yainage90/fashion-object-detection"  # ①번: 옷 위치(bbox) + 큰 카테고리 탐지
LABELING_MODEL_NAME = "patrickjohncyh/fashion-clip"  # ②번: 세부 라벨링 (zero-shot 분류)

# 탐지 모델 로딩 — 이 파일이 import되는 순간(서버가 뜰 때) 딱 한 번만 실행됨
detection_processor = AutoImageProcessor.from_pretrained(DETECTION_MODEL_NAME)  # 이미지를 모델 입력 형태로 전처리
detection_model = AutoModelForObjectDetection.from_pretrained(DETECTION_MODEL_NAME)  # 탐지 모델 본체
detection_model.eval()  # 추론 전용 모드로 전환 (학습 때만 쓰는 기능들을 꺼서 결과를 일정하게 만듦)

# 세부 라벨링 모델(FashionCLIP) 로딩
labeling_processor = CLIPProcessor.from_pretrained(LABELING_MODEL_NAME)  # 이미지+텍스트를 모델 입력 형태로 전처리
labeling_model = CLIPModel.from_pretrained(LABELING_MODEL_NAME)  # FashionCLIP 모델 본체
labeling_model.eval()  # 역시 추론 전용 모드로 전환