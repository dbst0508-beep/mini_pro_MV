// Django가 브라우저에 심어둔 csrftoken 쿠키 값을 읽어오는 함수
function getCookie(name) {
    const value = `; ${document.cookie}`;      // 쿠키 전체를 세미콜론 붙여서 이어붙임
    const parts = value.split(`; ${name}=`);   // "csrftoken=" 기준으로 문자열을 자름
    if (parts.length === 2) {
        return parts.pop().split(";").shift(); // 원하는 값만 뽑아냄
    }
}

const csrftoken = getCookie("csrftoken");  // 이 페이지의 CSRF 토큰 값을 미리 읽어둠

// class="like-button"인 버튼을 전부 찾아서, 각각에 클릭 이벤트를 등록
document.querySelectorAll(".like-button").forEach((button) => {
    button.addEventListener("click", async () => {
        const postId = button.dataset.postId;  // HTML의 data-post-id 값을 읽음

        // 서버의 좋아요 토글 API로 POST 요청을 보냄
        const response = await fetch(`/api/posts/${postId}/like/`, {
            method: "POST",
            headers: {
                "X-CSRFToken": csrftoken,  // 1단계에서 설명한 그 보안 토큰을 실어 보냄
            },
        });

        const data = await response.json();  // 서버 응답(JSON)을 자바스크립트 객체로 변환

        // 서버가 알려준 결과에 따라 버튼 모양을 바꿈
        if (data.liked) {
            button.classList.add("liked");
            button.textContent = `♥ ${data.like_count}`;  // 서버가 준 최신 개수를 그대로 표시
        } else {
            button.classList.remove("liked");
            button.textContent = `♡ ${data.like_count}`;
        }
    });
});
