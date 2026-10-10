import torch  # 추론 중 불필요한 계산을 끄는 데 씀
from .ml_models import labeling_processor, labeling_model  # FashionCLIP 모델/전처리기

# 카테고리별 세부 라벨 후보: (영어 후보 텍스트, 한글 라벨) — 어제 만든 목록
LABEL_CANDIDATES = {
    "상의": [
        ("a photo of a t-shirt", "반팔 티셔츠"),
        ("a photo of a long sleeve t-shirt", "긴팔 티셔츠"),
        ("a photo of a shirt", "셔츠"),
        ("a photo of a blouse", "블라우스"),
        ("a photo of a knit sweater", "니트"),
        ("a photo of a hoodie", "후드티"),
        ("a photo of a sweatshirt", "맨투맨"),
        ("a photo of a crop top", "크롭탑"),
    ],
    "하의": [
        ("a photo of jeans", "청바지"),
        ("a photo of slacks", "슬랙스"),
        ("a photo of chino pants", "치노팬츠"),
        ("a photo of shorts", "반바지"),
        ("a photo of a skirt", "스커트"),
        ("a photo of leggings", "레깅스"),
        ("a photo of jogger pants", "조거팬츠"),
        ("a photo of cargo pants", "카고팬츠"),
    ],
    "아우터": [
        ("a photo of a coat", "코트"),
        ("a photo of a jacket", "자켓"),
        ("a photo of a cardigan", "가디건"),
        ("a photo of a puffer jacket", "패딩"),
        ("a photo of a blazer", "블레이저"),
        ("a photo of a trench coat", "트렌치코트"),
        ("a photo of a denim jacket", "데님자켓"),
    ],
    "원피스": [
        ("a photo of a mini dress", "미니드레스"),
        ("a photo of a midi dress", "미디드레스"),
        ("a photo of a maxi dress", "맥시드레스"),
        ("a photo of a shirt dress", "셔츠원피스"),
        ("a photo of a knit dress", "니트원피스"),
    ],
    "신발": [
        ("a photo of sneakers", "스니커즈"),
        ("a photo of dress shoes", "구두"),
        ("a photo of loafers", "로퍼"),
        ("a photo of boots", "부츠"),
        ("a photo of sandals", "샌들"),
        ("a photo of heels", "힐"),
    ],
    "가방": [
        ("a photo of a backpack", "백팩"),
        ("a photo of a tote bag", "토트백"),
        ("a photo of a crossbody bag", "크로스백"),
        ("a photo of a clutch", "클러치"),
        ("a photo of a shoulder bag", "숄더백"),
    ],
    "모자": [
        ("a photo of a baseball cap", "볼캡"),
        ("a photo of a bucket hat", "버킷햇"),
        ("a photo of a beanie", "비니"),
    ],
}


def crop_item(image, item):
    """정규화된 bbox(0~1)를 원본 이미지 픽셀 크기로 환산해서 그 영역만 잘라냄"""
    image_width, image_height = image.size
    x_min = item["bbox_x"] * image_width
    y_min = item["bbox_y"] * image_height
    x_max = x_min + item["bbox_width"] * image_width
    y_max = y_min + item["bbox_height"] * image_height
    return image.crop((x_min, y_min, x_max, y_max))


def label_item(image, item):
    """탐지된 아이템 하나를 크롭해서 FashionCLIP으로 세부 라벨을 붙임"""
    candidates = LABEL_CANDIDATES.get(item["category"], [])  # 이 카테고리의 후보 목록 꺼내기
    if not candidates:
        return ""  # 후보 목록에 없는 카테고리면 라벨 없이 넘어감

    cropped = crop_item(image, item)  # 박스 영역만 잘라낸 이미지
    texts = [text for text, _ in candidates]  # 영어 후보 텍스트만 리스트로 추출

    inputs = labeling_processor(text=texts, images=cropped, return_tensors="pt", padding=True)

    with torch.no_grad():
        outputs = labeling_model(**inputs)

    probs = outputs.logits_per_image.softmax(dim=1)  # 후보들 각각에 대한 확률로 변환
    best_index = probs.argmax().item()  # 확률이 가장 높은 후보의 인덱스

    return candidates[best_index][1]  # 그 인덱스의 한글 라벨 반환


def label_items(image, items):
    """detect_items()가 만든 리스트 각각에 label 필드를 채워서 돌려줌"""
    for item in items:
        item["label"] = label_item(image, item)
    return items
