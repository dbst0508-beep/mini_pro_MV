# AI 분석 결과 화면 개선 (사진 위 박스 · 비율 막대 · 아이템 카드) — 2026-10-14

## 1. 기술문서

### 한 줄 요약
글자만 나열하던 분석 결과 화면을 **사진 위에 번호 박스, 스타일 비율 막대, 아이템 카드**로 바꿨다. 두 결과 페이지가 따로 갖고 있던 본문을 조각 하나로 합쳤고, 재분석이 실패해도 이전에 성공한 결과가 가려지지 않게 했다.

### 고친 문제 세 가지

| 문제 | 고치기 전 | 고친 후 |
|---|---|---|
| 게시물 분석 결과에 사진이 없음 | 해석문은 "크롭 기장의 가죽 재킷..."이라고 하는데 사진을 볼 수 없음 | 사진이 함께 표시됨 |
| 결과가 글자 나열 | `시크: 55.0%`, `하의 - 레더 미니스커트` 같은 줄글 | 박스, 막대, 카드 |
| 재분석 실패가 이전 결과를 가림 | 성공한 결과가 있어도 실패 문구만 보임 | 이전 결과를 보여 주고 실패 사실은 안내 문구로 |

이 프로젝트의 목적은 패션을 잘 모르는 사람이 잘 입은 사람의 착장을 보면서 왜 좋은지 배우는 것이다. 사진 없이 해석문만 보이는 화면은 그 목적의 절반을 빼먹고 있었다.

### 화면 구성 (완료 상태)
```
← 돌아가기 링크
[재분석 실패 안내]            ← 해당할 때만
┌──────────────────────┐
│  사진                 │
│   ┌②┐                │    ← 탐지된 아이템 위치에 번호 박스
│  ┌④──┬③─┐            │
│  │   └───┘            │
│  ├①───┐               │
└──────────────────────┘
AI 스타일 분석 결과

스타일 비율
시크     ████████░░░░  55%   ← 큰 것부터
스트릿   ██████░░░░░░  45%

스타일 해석
(옅은 바탕의 해석문)

탐지된 아이템
① 하의  레더 미니스커트   [쇼핑 검색]   ← 사진의 번호와 같은 번호
② 모자  블랙 볼캡         [쇼핑 검색]
```

### 구조 변경: 두 페이지가 조각 하나를 함께 씀
```
[고치기 전]
result.html            : 결과 표시 코드 (사진 없음)
standalone_result.html : 거의 같은 결과 표시 코드 (사진 있음)

[고친 후]
result.html            ─┐
                        ├─→ _result_body.html (사진 + 박스 + 결과/실패/분석 중)
standalone_result.html ─┘
```
피드와 게시글 상세 페이지가 `_post_card.html`을 함께 쓰는 것과 같은 방식이다. 같은 내용을 두 군데에 적어 두면 한쪽만 고치고 다른 쪽을 잊게 되는데, 사진이 한쪽에만 있던 것이 바로 그렇게 생긴 어긋남이었다.

### 박스 위치를 정하는 방법
탐지 모델이 찾은 위치는 DB에 **0~1 사이의 비율**로 저장돼 있다(예: 왼쪽에서 0.22, 위에서 0.40). 이 값은 처음부터 저장하고 있었지만 화면에서 쓴 적이 없었다.

화면에서는 이 비율에 100을 곱해 `left: 22%; top: 40%`처럼 CSS 위치로 쓴다. 비율이라서 사진이 어떤 크기로 표시되든 박스가 같은 자리에 온다.

### 재분석 실패 시 보여 줄 분석을 고르는 규칙 (게시물 기반 결과 페이지)

| 가장 최근 분석 | 그 전에 완료된 분석 | 화면 |
|---|---|---|
| 완료 | (상관없음) | 가장 최근 결과 |
| 대기중/분석중 | (상관없음) | "분석 중입니다..." |
| 실패 | 있음 | **이전 완료 결과 + 재분석 실패 안내** |
| 실패 | 없음 | 실패 문구 |
| 없음 | 없음 | "아직 분석 요청이 없습니다" |

### 신규/변경 파일

| 파일 | 상태 | 내용 |
|---|---|---|
| `templates/analysis/_result_body.html` | 신규 | 두 결과 페이지가 함께 쓰는 본문 조각 |
| `templates/analysis/result.html` | 수정 | 본문을 조각으로 교체, 재분석 실패 안내 추가 |
| `templates/analysis/standalone_result.html` | 수정 | 본문을 조각으로 교체 |
| `static/css/analysis.css` | 수정 | 결과 화면용 스타일 22개 규칙 추가 |
| `analysis/models.py` | 수정 | `Analysis.source_image` 추가 (마이그레이션 없음) |
| `analysis/tasks.py` | 수정 | 사진 고르는 부분을 `source_image`로 교체 |
| `analysis/views.py` | 수정 | `result`에 이전 완료 결과 찾기 추가 |
| `analysis/tests.py` | 수정 | 결과 페이지 테스트 3개 추가 (15개 → 18개) |
| `README.md` | 수정 | 결과 화면 설명 추가, 테스트 개수 갱신 |

URL과 JS는 수정하지 않았다.

---

## 2. 클래스·함수 단위 코드리뷰

### `Analysis.source_image` — 같은 판단을 한 곳으로
"이 분석의 사진은 어디에 있나"는 두 가지 경우가 있다. 단독 업로드면 분석 자체의 `image`, 게시물 기반이면 게시물의 `image`. 이 판단을 `tasks.py`가 이미 하고 있었는데, 이번에 템플릿에서도 필요해졌다. 두 군데에 같은 판단을 적는 대신 모델에 한 번 적고 양쪽에서 가져다 쓴다.

`@property`를 붙였기 때문에 `analysis.source_image`처럼 괄호 없이 값처럼 쓴다. DB의 칸이 아니라 그때그때 계산해서 돌려주는 값이라서 마이그레이션이 필요 없다.

이게 없었다면 템플릿에서 `analysis.image.url`을 썼을 텐데, 게시물 기반 분석은 `image`가 비어 있어서 `.url`을 꺼내는 순간 에러가 난다.

### `_result_body.html` — `{% with %}`로 목록을 한 번만 꺼냄
아이템 목록을 사진 위 박스와 아래 카드, 두 곳에서 쓴다. `{% with items=analysis.detected_items.all %}`로 한 번 꺼내 이름을 붙여 두고 양쪽에서 쓴다. 같은 목록을 쓰기 때문에 박스의 3번과 카드의 3번이 반드시 같은 아이템이다.

### `{% widthratio %}` — 템플릿에서 곱하기
Django 템플릿에는 곱하기가 없다. `{% widthratio item.bbox_x 1 100 %}`는 `값 ÷ 1 × 100`을 계산해 정수로 돌려준다. 0.223이 22가 된다.

짚어 둘 점: 정수로 반올림되므로 박스 위치가 최대 0.5%까지 어긋날 수 있다. 화면 폭 600px 기준으로 3px 정도라 눈에 띄지 않는다.

뷰에서 미리 계산해 넘기는 방법도 있었지만, 그러면 뷰가 화면 표시용 숫자까지 만들어야 한다. 표시 방식에 관한 일은 템플릿에 두는 쪽을 택했다.

### 박스는 완료 상태에서만 그림
사진은 상태와 무관하게 항상 보여 주고, 박스는 `{% if analysis.status == "completed" %}` 안에 넣었다. 분석 중이거나 실패했을 때도 "어떤 사진을 분석하고 있는지"는 보여야 하기 때문이다.

### `|dictsortreversed:"ratio"` — 큰 비율부터
DB에서 꺼낸 순서는 저장된 순서일 뿐이다. 가장 비중이 큰 스타일이 맨 위에 와야 읽기 좋으므로 템플릿에서 정렬했다.

### 라벨이 없을 때의 처리
이전에는 `{{ item.category }} - {{ item.label }}`로 적어서 라벨이 비면 "상의 - "처럼 어색하게 나왔다. 실제 CV 모델을 연동한 날부터 적어 둔 숙제였다. 이번에 `{% if item.label %}`로 감싸 라벨이 없으면 카테고리만 나오게 했고, 검색 링크가 없으면 쇼핑 검색 버튼도 나오지 않는다.

### CSS — 박스가 사진 기준으로 놓이게 하는 세 줄
- `.analysis-result__frame { position: relative; display: inline-block; }`
- `.analysis-result__box { position: absolute; }`

`position: absolute`인 요소는 가장 가까운 `position: relative` 조상을 기준으로 위치를 잡는다. 그래서 박스의 `left: 22%`는 틀의 폭의 22%가 된다.

`display: inline-block`이 핵심이다. 이게 없으면 틀이 화면 폭 전체로 늘어나서 `22%`가 사진이 아니라 화면 기준이 되어 박스가 어긋난다. `inline-block`은 틀을 안의 사진 크기에 딱 맞게 줄여 준다.

### CSS — 번호 원 하나를 두 곳에서
`.analysis-result__badge`는 박스 모서리에 붙는 번호 원이다. 카드 안에서는 같은 모양에 `--inline`을 덧붙여 `position: static`으로 제자리에 놓는다. 모양 정의는 한 번만 하고 위치만 바꾼 것이다.

### 이전 스타일 이름을 남겨 둔 것
실패 문구와 "분석 중" 문구는 예전의 `.analysis-placeholder__desc` 클래스를 그대로 쓴다. 업로드 폼 페이지(`home.html`)가 아직 `analysis-placeholder` 계열을 쓰고 있어서 지우지 않았다. 이름이 "placeholder(준비 중)"인데 실제 화면에 쓰이고 있는 것은 어색한 점이다.

### `result` 뷰 — 실패했을 때만 한 번 더 찾기
가장 최근 분석이 실패가 아닐 때는 이전과 똑같이 동작한다. 실패일 때만 완료된 분석을 한 번 더 찾는다. 찾으면 화면에는 그것을 보여 주고, 실패한 분석은 `failed_retry`라는 이름으로 따로 넘겨 안내 문구에 쓴다.

짚어 둘 점: 재분석이 **진행 중**일 때는 이전 결과를 보여 주지 않고 "분석 중입니다..."만 나온다. 곧 새 결과로 바뀔 것이므로 그대로 뒀다.

### 단독 업로드 쪽에는 이 처리가 없는 이유
단독 업로드 결과 페이지는 주소가 분석 번호 하나를 가리킨다(`/analysis/34/result/`). "이 사진의 이전 분석"이라는 개념이 없어서 해당하지 않는다.

### 결과 페이지 테스트 — `assertContains`
지금까지의 테스트는 DB 값이나 상태 코드를 확인했다. 이번 세 개는 `assertContains`로 **응답으로 온 화면 안에 특정 글자가 들어 있는지**를 확인한다. 템플릿을 실제로 그려 보는 테스트라서 템플릿의 문법 오류도 함께 잡는다.

어제 테스트를 작성할 때 "결과 페이지는 화면을 고친 뒤에 쓰자"고 미뤄 둔 것을 이번에 채웠다.

---

## 3. 코드 한 줄 한 줄 주석

### `analysis/models.py` (`Analysis` 클래스에 추가한 부분)
```python
    @property  # analysis.source_image 처럼 괄호 없이 값처럼 꺼내 쓸 수 있게 해주는 표시
    def source_image(self):  # DB 칸이 아니라 부를 때마다 계산해서 돌려주는 값
        """분석 대상 사진: 독립 업로드면 image, 게시물 기반이면 post.image"""
        return self.image if self.image else self.post.image  # 자체 사진이 있으면 그것, 없으면 게시물의 사진
```

### `analysis/tasks.py` (바뀐 한 줄)
```python
    image_field = analysis.source_image  # 게시물 기반이면 게시물 사진, 독립 업로드면 업로드한 사진 (models.py 참고)
```

### `analysis/views.py` (`result` 함수 전체)
```python
def result(request, post_id):
    post = get_object_or_404(Post, pk=post_id)                        # 결과를 볼 게시물 조회
    analysis = post.analyses.order_by("-created_at").first()             # 가장 최근 분석 기록 (없으면 None)
    failed_retry = None                                                  # "실패한 재분석" 자리 (기본은 없음)

    if analysis and analysis.status == Analysis.STATUS_FAILED:           # 가장 최근 분석이 실패했다면
        last_completed = post.analyses.filter(                            # 이 게시물의 분석 중에서
            status=Analysis.STATUS_COMPLETED                               # 완료된 것만 골라
        ).order_by("-created_at").first()                                  # 그중 가장 최근 것
        if last_completed:                                                # 이전에 성공한 결과가 있으면
            failed_retry = analysis                                        # 실패한 것은 안내용으로 따로 두고
            analysis = last_completed                                      # 화면에는 성공한 결과를 보여줌

    return render(request, "analysis/result.html", {                   # 템플릿에 세 가지를 넘김
        "post": post,                                                    # 게시물 (돌아가기 링크에 사용)
        "analysis": analysis,                                            # 화면에 보여줄 분석
        "failed_retry": failed_retry,                                    # 실패한 재분석 (없으면 None)
    })
```

### `templates/analysis/_result_body.html` (전체)
```django
{# 분석 결과 본문 — result.html과 standalone_result.html이 함께 쓰는 조각. 필요한 값: analysis #}
{% with items=analysis.detected_items.all %}                          {# 아이템 목록을 한 번만 꺼내서 박스와 카드가 같은 순서를 쓰게 함 #}

<div class="analysis-result__photo">                                  {# 사진을 가운데 놓는 바깥 상자 #}
    <div class="analysis-result__frame">                              {# 사진 크기에 딱 맞는 틀 — 박스 위치의 기준이 됨 #}
        <img src="{{ analysis.source_image.url }}" alt="분석한 사진" class="analysis-result__image">  {# 분석 대상 사진 #}
        {% if analysis.status == "completed" %}                       {# 분석이 끝났을 때만 박스를 그림 #}
            {% for item in items %}                                   {# 탐지된 아이템마다 박스 하나 #}
            <div class="analysis-result__box"
                 style="left: {% widthratio item.bbox_x 1 100 %}%; top: {% widthratio item.bbox_y 1 100 %}%; width: {% widthratio item.bbox_width 1 100 %}%; height: {% widthratio item.bbox_height 1 100 %}%;">  {# 0~1 비율을 %로 바꿔 위치와 크기 지정 #}
                <span class="analysis-result__badge">{{ forloop.counter }}</span>  {# 1부터 시작하는 번호 #}
            </div>
            {% endfor %}
        {% endif %}
    </div>
</div>

{% if analysis.status == "completed" %}                               {# 분석 완료 상태면 결과 전부 표시 #}
    <h1 class="analysis-result__title">AI 스타일 분석 결과</h1>        {# 결과 제목 #}

    <section class="analysis-result__section">                        {# 구역 1: 스타일 비율 #}
        <h2 class="analysis-result__heading">스타일 비율</h2>
        {% for score in analysis.style_scores.all|dictsortreversed:"ratio" %}  {# 비율이 큰 것부터 #}
        <div class="analysis-result__score">                          {# 한 줄: 이름 / 막대 / 숫자 #}
            <span class="analysis-result__score-name">{{ score.style_name }}</span>  {# 스타일 이름 #}
            <div class="analysis-result__bar">                        {# 막대의 옅은 바탕 #}
                <div class="analysis-result__bar-fill" style="width: {{ score.ratio|floatformat:0 }}%;"></div>  {# 비율만큼 막대를 채움 #}
            </div>
            <span class="analysis-result__score-ratio">{{ score.ratio|floatformat:0 }}%</span>  {# 소수점 없이 숫자 표시 #}
        </div>
        {% endfor %}
    </section>

    <section class="analysis-result__section">                        {# 구역 2: 스타일 해석 #}
        <h2 class="analysis-result__heading">스타일 해석</h2>
        <p class="analysis-result__interpretation">{{ analysis.interpretation }}</p>  {# Gemini가 쓴 해석문 #}
    </section>

    <section class="analysis-result__section">                        {# 구역 3: 탐지된 아이템 #}
        <h2 class="analysis-result__heading">탐지된 아이템</h2>
        <ul class="analysis-result__items">
            {% for item in items %}                                   {# 위의 박스와 같은 목록, 같은 순서 #}
            <li class="analysis-result__item">                        {# 아이템 카드 하나 #}
                <span class="analysis-result__badge analysis-result__badge--inline">{{ forloop.counter }}</span>  {# 사진 위 박스와 같은 번호 #}
                <div class="analysis-result__item-text">              {# 카테고리와 라벨을 세로로 쌓는 상자 #}
                    <span class="analysis-result__item-category">{{ item.category }}</span>  {# 큰 분류 (작은 글씨) #}
                    {% if item.label %}<span class="analysis-result__item-label">{{ item.label }}</span>{% endif %}  {# 라벨이 없으면 카테고리만 #}
                </div>
                {% if item.search_url %}                              {# 검색 링크가 있을 때만 버튼 표시 #}
                <a href="{{ item.search_url }}" target="_blank" rel="noopener" class="btn btn--ghost">쇼핑 검색</a>  {# 새 탭으로 쇼핑 검색 #}
                {% endif %}
            </li>
            {% endfor %}
        </ul>
    </section>

{% elif analysis.status == "failed" %}                                {# 실패 상태면 에러 메시지 #}
    <p class="analysis-placeholder__desc">분석에 실패했습니다: {{ analysis.error_message }}</p>

{% else %}                                                            {# 대기중/분석중이면 폴링 #}
    <div class="analysis-polling" data-status-url="{% url 'analysis:status' analysis.id %}">  {# JS가 이 주소로 3초마다 상태 확인 #}
        <p class="analysis-placeholder__desc">분석 중입니다... 완료되면 자동으로 새로고침됩니다.</p>
    </div>
{% endif %}

{% endwith %}
```

### `templates/analysis/result.html` (`content` 블록)
```django
{% block content %}
<div class="analysis-result">                                         {# 결과 페이지 전체를 감싸는 상자 #}
    <a href="{% url 'posts:detail' post.id %}" class="detail__back">← 게시글로 돌아가기</a>  {# 게시글 상세로 돌아가는 링크 #}

    {% if analysis %}                                                 {# 보여줄 분석이 있으면 #}
        {% if failed_retry %}                                         {# 재분석은 실패했지만 이전 결과가 있을 때 #}
        <p class="analysis-result__notice">최근 재분석에 실패해 이전 분석 결과를 보여드립니다. ({{ failed_retry.error_message }})</p>  {# 실패 사실과 이유 안내 #}
        {% endif %}
        {% include "analysis/_result_body.html" %}                    {# 사진 + 결과/실패/분석 중 화면 (공용 조각) #}
    {% else %}                                                        {# analysis 자체가 None이면 (아직 요청 안 함) #}
        <p class="analysis-placeholder__desc">아직 분석 요청이 없습니다.</p>
    {% endif %}
</div>
{% endblock %}
```

### `templates/analysis/standalone_result.html` (`content` 블록)
```django
{% block content %}
<div class="analysis-result">                                         {# 결과 페이지 전체를 감싸는 상자 #}
    <a href="{% url 'analysis:home' %}" class="detail__back">← AI 분석으로 돌아가기</a>  {# B 플로우는 게시글이 없어서 analysis:home으로 #}

    {% include "analysis/_result_body.html" %}                        {# 사진 + 결과/실패/분석 중 화면 (공용 조각) #}
</div>
{% endblock %}
```

### `static/css/analysis.css` (추가한 부분 전체)
```css
/* ===== 분석 결과 페이지 ===== */
.analysis-result {
    padding: var(--space-lg) var(--space-md);         /* 위아래 24px, 좌우 16px */
}

.analysis-result__photo {
    display: flex;                                   /* 안의 사진 틀을 가운데 놓기 위한 flex 컨테이너 */
    justify-content: center;                          /* 가로 가운데 정렬 */
    margin: var(--space-md) 0 var(--space-lg);         /* 위 16px, 아래 24px */
}

.analysis-result__frame {
    position: relative;                              /* 안의 박스들이 이 틀을 기준으로 위치를 잡게 함 */
    display: inline-block;                            /* 사진 크기에 딱 맞게 줄어듦 (그래야 %가 사진 기준이 됨) */
    max-width: 100%;                                   /* 화면보다 넓어지지 않게 */
    border-radius: var(--radius-md);                    /* 카드급 둥근모서리 */
    overflow: hidden;                                    /* 둥근모서리 밖으로 삐져나온 부분 숨김 */
    border: 1px solid var(--color-border);                /* 얇은 테두리 */
}

.analysis-result__image {
    display: block;                                  /* 사진 아래 생기는 미세한 빈틈 제거 */
    max-width: 100%;                                  /* 틀 폭 안으로 제한, 비율은 유지 */
}

.analysis-result__box {
    position: absolute;                              /* 틀 안에서 left/top/width/height(%)로 위치 지정 */
    box-sizing: border-box;                           /* 테두리 두께를 크기 안에 포함 */
    border: 2px solid var(--color-accent);             /* 포인트 컬러 테두리 */
    border-radius: var(--radius-sm);                    /* 살짝 둥글게 */
}

.analysis-result__badge {
    position: absolute;                              /* 박스의 왼쪽 위 모서리에 붙임 */
    top: -2px;                                        /* 테두리 두께만큼 올려서 모서리에 딱 맞춤 */
    left: -2px;                                        /* 테두리 두께만큼 왼쪽으로 */
    width: 20px;                                        /* 번호 원 지름 */
    height: 20px;                                        /* 번호 원 지름 */
    border-radius: 50%;                                   /* 원형 */
    background: var(--color-accent);                       /* 포인트 컬러 배경 */
    color: #ffffff;                                         /* 흰 글자 */
    font-size: 12px;                                         /* 작은 번호 */
    font-weight: 600;                                         /* 살짝 굵게 */
    line-height: 20px;                                         /* 원 높이와 같게 해서 세로 가운데 */
    text-align: center;                                         /* 가로 가운데 */
}

.analysis-result__badge--inline {
    position: static;                                /* 아이템 카드 안에서는 모서리에 붙이지 않고 제자리에 */
    flex-shrink: 0;                                   /* 글자가 길어져도 원이 찌그러지지 않게 */
}

.analysis-result__title {
    font-size: 20px;                                 /* 페이지 제목 크기 */
    text-align: center;                               /* 가운데 정렬 */
    margin: 0 0 var(--space-lg) 0;                     /* 아래 24px */
}

.analysis-result__section {
    margin-bottom: var(--space-lg);                  /* 구역 사이 간격 24px */
}

.analysis-result__heading {
    font-size: 15px;                                 /* 구역 제목 크기 */
    margin: 0 0 var(--space-sm) 0;                     /* 아래 8px */
    color: var(--color-text);                           /* 기본 글자색 */
}

.analysis-result__score {
    display: flex;                                   /* 이름 / 막대 / 숫자를 가로로 배치 */
    align-items: center;                              /* 세로 가운데 정렬 */
    gap: var(--space-sm);                              /* 사이 간격 8px */
    margin-bottom: var(--space-sm);                     /* 줄 사이 간격 8px */
    font-size: 14px;                                     /* 본문 크기 */
}

.analysis-result__score-name {
    width: 72px;                                     /* 이름 칸 폭을 고정해 막대 시작 위치를 맞춤 */
    flex-shrink: 0;                                   /* 줄어들지 않게 */
}

.analysis-result__bar {
    flex: 1;                                         /* 남는 폭을 전부 차지 */
    height: 10px;                                     /* 막대 두께 */
    background: var(--color-accent-soft);              /* 옅은 바탕 */
    border-radius: 999px;                               /* 양끝을 완전히 둥글게 */
    overflow: hidden;                                    /* 채워진 부분이 둥근 바탕 밖으로 안 나가게 */
}

.analysis-result__bar-fill {
    height: 100%;                                    /* 바탕 높이만큼 */
    background: var(--color-accent);                  /* 포인트 컬러로 채움 */
    border-radius: 999px;                              /* 끝을 둥글게 */
}

.analysis-result__score-ratio {
    width: 40px;                                     /* 숫자 칸 폭 고정 */
    text-align: right;                                /* 오른쪽 정렬 */
    color: var(--color-text-muted);                    /* 보조 글자색 */
}

.analysis-result__interpretation {
    font-size: 14px;                                 /* 본문 크기 */
    line-height: 1.7;                                 /* 긴 글을 읽기 편하게 줄간격 넓힘 */
    margin: 0;                                         /* 기본 마진 제거 */
    padding: var(--space-md);                           /* 안쪽 여백 16px */
    background: var(--color-bg);                         /* 옅은 회색 바탕 */
    border-radius: var(--radius-md);                      /* 카드급 둥근모서리 */
}

.analysis-result__items {
    list-style: none;                                /* 기본 점(•) 제거 */
    margin: 0;                                        /* 기본 마진 제거 */
    padding: 0;                                        /* 기본 들여쓰기 제거 */
}

.analysis-result__item {
    display: flex;                                   /* 번호 / 글자 / 버튼을 가로로 배치 */
    align-items: center;                              /* 세로 가운데 정렬 */
    gap: var(--space-md);                              /* 사이 간격 16px */
    padding: var(--space-md);                           /* 안쪽 여백 16px */
    border: 1px solid var(--color-border);               /* 얇은 테두리 */
    border-radius: var(--radius-md);                      /* 카드급 둥근모서리 */
    margin-bottom: var(--space-sm);                        /* 카드 사이 간격 8px */
}

.analysis-result__item-text {
    flex: 1;                                         /* 남는 폭을 차지해서 버튼을 오른쪽 끝으로 밀어냄 */
    display: flex;                                    /* 카테고리와 라벨을 세로로 쌓기 위해 */
    flex-direction: column;                            /* 세로 방향 */
}

.analysis-result__item-category {
    font-size: 12px;                                 /* 작은 보조 글씨 */
    color: var(--color-text-muted);                   /* 보조 글자색 */
}

.analysis-result__item-label {
    font-size: 15px;                                 /* 아이템 이름은 조금 크게 */
    font-weight: 600;                                 /* 굵게 */
}

.analysis-result__notice {
    font-size: 13px;                                 /* 안내 문구는 작게 */
    line-height: 1.5;                                 /* 두 줄이 될 때 읽기 편하게 */
    color: var(--color-text-muted);                    /* 보조 글자색 */
    background: var(--color-bg);                        /* 옅은 회색 바탕 */
    border: 1px solid var(--color-border);               /* 얇은 테두리 */
    border-radius: var(--radius-sm);                      /* 살짝 둥글게 */
    padding: var(--space-sm) var(--space-md);              /* 위아래 8px, 좌우 16px */
    margin: var(--space-md) 0 0 0;                          /* 위쪽 16px */
}
```

### `analysis/tests.py` (추가한 클래스)
```python
# 결과 페이지 테스트 코드 (게시물 기반)
class ResultViewTests(AnalysisTestCase):
    def setUp(self):
        super().setUp()  # 공통 준비물(유저/게시물/분석) 먼저
        self.url = reverse("analysis:result", args=[self.post.id])  # 이 게시물의 결과 페이지 주소

    def complete(self, analysis):  # 분석을 "완료" 상태로 만드는 도우미
        Analysis.objects.filter(pk=analysis.pk).update(status=Analysis.STATUS_COMPLETED)  # DB에서 바로 상태 변경

    def add_failed_retry(self):  # 나중에 요청한 재분석이 실패한 상황을 만드는 도우미
        return Analysis.objects.create(  # 같은 게시물에 분석을 하나 더 만듦
            post=self.post, callback_token="retry-token",  # 토큰은 겹치면 안 되므로 다른 값
            status=Analysis.STATUS_FAILED, error_message="재분석 실패 문구",  # 실패 상태 + 안내 문구
        )

    def test_completed_result_shows_photo_and_title(self):
        self.complete(self.analysis)  # 분석을 완료 상태로
        response = self.client.get(self.url)  # 결과 페이지 열기

        self.assertContains(response, self.post.image.url)  # 게시물 사진이 화면에 있어야 함
        self.assertContains(response, "AI 스타일 분석 결과")  # 결과 제목이 나와야 함

    def test_failed_retry_falls_back_to_previous_completed(self):
        self.complete(self.analysis)  # 먼저 성공한 분석이 있고
        self.add_failed_retry()  # 그 뒤의 재분석은 실패
        response = self.client.get(self.url)  # 결과 페이지 열기

        self.assertContains(response, "AI 스타일 분석 결과")  # 이전에 성공한 결과를 보여줘야 함
        self.assertContains(response, "이전 분석 결과를 보여드립니다")  # 재분석이 실패했다는 안내도 있어야 함
        self.assertContains(response, "재분석 실패 문구")  # 실패 이유도 함께

    def test_failed_without_previous_shows_error(self):
        Analysis.objects.filter(pk=self.analysis.pk).update(  # 하나뿐인 분석을
            status=Analysis.STATUS_FAILED, error_message="첫 분석 실패 문구",  # 실패 상태로 만듦
        )
        response = self.client.get(self.url)  # 결과 페이지 열기

        self.assertContains(response, "분석에 실패했습니다")  # 보여줄 이전 결과가 없으니 실패 화면
        self.assertNotContains(response, "AI 스타일 분석 결과")  # 결과 제목은 나오면 안 됨
```

---

## 4. 복습 (이번에 새로 익힌 개념)

### 같은 내용은 한 곳에만 적는다
두 결과 페이지에 거의 같은 코드가 따로 있었고, 그 결과 한쪽에만 사진이 있는 어긋남이 생겼다. 조각(`{% include %}`)으로 합치면 한 번 고친 것이 양쪽에 반영된다. `source_image`도 같은 생각이다. "어느 사진을 쓰나"라는 판단을 `tasks.py`와 템플릿에 각각 적는 대신 모델에 한 번만 적었다.

### `@property`
메서드를 값처럼 꺼내 쓰게 해 주는 표시. `analysis.source_image()`가 아니라 `analysis.source_image`로 쓴다. DB의 칸이 아니라 계산된 값이라 마이그레이션이 필요 없고, 템플릿에서도 그대로 쓸 수 있다.

### 비율로 저장하면 어떤 크기에서도 맞는다
위치를 픽셀이 아니라 0~1 비율로 저장해 둔 덕분에, 화면에 사진이 어떤 크기로 나오든 `%`로 바꾸기만 하면 박스가 제자리에 온다. 탐지 모델을 연동할 때 "DB 저장용은 정규화"로 정한 결정이 여기서 쓰였다.

### `position: relative`와 `absolute`
`absolute`인 요소는 가장 가까운 `relative` 조상을 기준으로 위치를 잡는다. "이 상자 안에서 여기"라고 말하려면 바깥 상자에 `relative`를, 안의 요소에 `absolute`를 준다.

### `display: inline-block`으로 내용 크기에 맞추기
보통의 `div`는 가로로 꽉 찬다. `inline-block`은 안의 내용 크기만큼만 차지한다. 사진 틀이 사진 크기와 같아야 `%` 위치가 사진 기준이 되므로 이게 필요했다.

### 템플릿 도구 네 가지
- `{% with 이름=값 %}`: 값에 이름을 붙여 여러 번 쓴다.
- `{% widthratio 값 1 100 %}`: 템플릿에서 곱하기를 하는 방법. 결과는 정수.
- `|dictsortreversed:"칸이름"`: 목록을 그 칸 기준으로 큰 것부터 정렬.
- `|floatformat:0`: 소수점 없이 표시.

### `{% if %}`는 연 만큼 닫아야 한다
`{% if %}`를 열면 반드시 `{% endif %}`로 닫아야 하고, 개수가 맞아야 한다. 하나라도 안 닫히면 Django는 `endif`가 나올 자리에 다른 것(`endblock`)이 나왔다고 알려 준다. 에러 메시지의 `'endblock', expected 'elif', 'else' or 'endif'`가 그 뜻이다.

### 에디터의 빨간 줄과 실제 에러는 다르다
VS Code가 `style="left: {% widthratio ... %}%"`에 빨간 줄을 그었지만 에러가 아니었다. 에디터는 이 파일을 일반 HTML로 읽기 때문에 Django 문법을 CSS 오류로 본다. 기준은 브라우저 화면과 터미널의 에러 메시지다.

### 보여 주는 것만 바꿀 때는 Django만 켜면 된다
서버 4개(Redis, cv_service, Celery, Django)는 새 분석을 만들 때 필요하다. 이미 끝난 분석은 결과가 DB에 있으므로 Django만 켜고 결과 주소로 들어가면 볼 수 있다. Gemini 한도도 쓰지 않는다.

### 테스트 결과는 "지금 저장된 파일" 기준이다
파일을 고치고 저장하기 전에 테스트를 돌리면 고치기 전 내용으로 돌아간다. 에러 메시지의 줄 번호가 지금 파일의 줄 수와 맞지 않으면 저장이 안 된 것을 의심한다.

---

## 5. 트러블슈팅

### 1) 게시물 분석 결과에 사진이 없음
- **발견**: 게시물 기반 분석을 처음 눌러 봤을 때 결과 화면에 사진 없이 글자만 나왔다. 단독 업로드 결과에는 사진이 있었다.
- **원인**: 결과 페이지가 두 템플릿으로 나뉘어 있었다. 게시물 쪽을 먼저 만들 때는 "사진은 게시글에 있으니 결과만 보여 주면 된다"는 식이었고, 나중에 만든 단독 업로드 쪽에만 사진을 넣었다. 버그라기보다 두 군데에 따로 적다가 생긴 어긋남이다.
- **해결**: 본문을 조각 하나(`_result_body.html`)로 합치고, 사진 고르는 판단을 `Analysis.source_image`로 모았다.

### 2) 재분석이 실패하면 이전에 성공한 결과까지 안 보임
- **발견**: 결과 화면을 확인하려고 게시물의 "AI 분석 결과 보기"를 눌렀는데 실패 문구만 나왔다. 그 게시물은 전날 분석에 성공한 적이 있었다.
- **원인**: 전날 실패 처리 테스트를 하면서 cv_service를 끄고 재분석을 요청했고, 그 실패한 분석이 가장 최근 것이 됐다. 뷰는 가장 최근 분석 하나만 보여 줬다.
- **해결**: 가장 최근 분석이 실패이고 그 전에 완료된 분석이 있으면, 완료된 것을 보여 주고 실패 사실은 안내 문구로 알린다.
- **배운 점**: 실패 처리를 만들 때는 "실패를 어떻게 기록하나"만 생각했고 "실패가 기존 결과에 어떤 영향을 주나"는 생각하지 못했다. 실제 데이터로 화면을 열어 보고서야 드러났다.

### 결과 검증
- **테스트**: `Ran 18 tests ... OK` (기존 15개 + 결과 페이지 3개).
- **단독 업로드 결과** (`/analysis/34/result/`): 사진 위에 박스 5개가 스커트·모자·상의·자켓·가방 위치에 맞게 그려지고, 번호가 아래 카드와 일치함. 스타일 막대가 큰 것부터 표시됨.
- **게시물 결과** (`/analysis/post/5/result/`): 고치기 전에는 실패 문구만 나왔고, 고친 후에는 재분석 실패 안내와 함께 이전 완료 결과(박스 5개)가 표시됨.
- 화면 확인은 Django 서버만 켜고 DB에 저장된 이전 분석 결과로 했다.

### 남은 관찰 사항
- **부츠에 박스가 없다.** 화면 문제가 아니라 탐지 모델이 놓친 것이다(`CONFIDENCE_THRESHOLD = 0.5` 조정 대상).
- **이번 브랜치에서 새 분석을 끝까지 돌려 보지는 않았다.** `tasks.py`의 `source_image` 변경은 `RunAnalysisTests`가 사진 파일을 실제로 여는 것까지 확인하지만, 서버 4개를 켠 전체 흐름은 머지 전에 한 번 돌려 볼 것.
- **박스가 겹치면 번호 원이 서로 가까이 붙는다.** 자켓과 상의처럼 겹치는 옷에서 보인다. 아이템 카드에 마우스를 올리면 해당 박스만 강조하는 식으로 개선할 수 있다.
