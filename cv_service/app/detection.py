import torch  # 추론 중 불필요한 계산(역전파)을 끄는 데 씀
from .ml_models import detection_processor, detection_model  # 방금 만든 모델/전처리기

# 모델이 영어로 내놓는 카테고리명 → 우리 DB에 저장할 한글 카테고리명 매핑
CATEGORY_KR = {
    "bag": "가방",
    "bottom": "하의",
    "dress": "원피스",
    "hat": "모자",
    "outer": "아우터",
    "shoes": "신발",
    "top": "상의",
}

CONFIDENCE_THRESHOLD = 0.5  # 모델이 "이거 맞다"고 확신하는 정도가 이 값 미만이면 결과에서 버림


def detect_items(image):
    """PIL Image를 받아서 [{category, bbox_x, bbox_y, bbox_width, bbox_height}, ...] 형태로 반환"""
    inputs = detection_processor(images=image, return_tensors="pt")  # 이미지를 모델이 이해하는 숫자 배열(텐서)로 변환

    with torch.no_grad():  # 추론만 할 거라 학습용 계산(기울기 추적)을 꺼서 속도/메모리 절약
        outputs = detection_model(**inputs)  # 실제 모델 추론 실행

    image_width, image_height = image.size  # bbox를 0~1로 정규화할 때 쓸 원본 이미지 크기(픽셀)
    target_sizes = torch.tensor([[image_height, image_width]])  # 후처리 함수가 요구하는 (세로, 가로) 순서

    results = detection_processor.post_process_object_detection(
        outputs, threshold=CONFIDENCE_THRESHOLD, target_sizes=target_sizes
    )[0]  # 모델의 날것 출력을 "박스+라벨+확신도" 형태로 정리해줌. [0]은 이미지 1장 중 첫 번째라는 뜻

    items = []
    for score, label_id, box in zip(results["scores"], results["labels"], results["boxes"]):
        label_en = detection_model.config.id2label[label_id.item()]  # 숫자 라벨(예: 3) → 영어 이름("top")으로 변환
        category = CATEGORY_KR.get(label_en, label_en)  # 위 매핑 테이블로 한글 변환, 매핑에 없으면 영어 그대로

        x_min, y_min, x_max, y_max = box.tolist()  # 픽셀 좌표 4개 (좌상단 x,y / 우하단 x,y)

        items.append({
            "category": category,
            "bbox_x": x_min / image_width,                    # 0~1 비율로 정규화
            "bbox_y": y_min / image_height,
            "bbox_width": (x_max - x_min) / image_width,
            "bbox_height": (y_max - y_min) / image_height,
        })

    return items