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
// class="comment-form"인 폼을 전부 찾아서, 각각에 제출 이벤트를 등록
document.querySelectorAll(".comment-form").forEach((form) => {
    form.addEventListener("submit", async (event) => {
        event.preventDefault();  // 폼의 기본 동작(페이지 새로고침)을 막음

        const section = form.closest(".comment-section");  // 이 폼을 감싸고 있는 댓글 영역(div)을 찾음
        const postId = section.dataset.postId;              // 그 영역에 심어둔 data-post-id 값을 읽음
        const input = form.querySelector(".comment-form__input");  // 폼 안의 입력창을 찾음
        const content = input.value;                         // 사용자가 입력창에 쓴 텍스트

        // 서버의 댓글 등록 API로 POST 요청을 보냄
        const response = await fetch(`/api/posts/${postId}/comments/`, {
            method: "POST",
            headers: {
                "X-CSRFToken": csrftoken,               // 좋아요 요청 때와 같은 CSRF 토큰
                "Content-Type": "application/json",     // 지금 보내는 내용물이 JSON 형식이라고 서버에 알림
            },
            body: JSON.stringify({ content: content }), // {content: "..."} 객체를 JSON 문자열로 바꿔서 담음
        });
        if (!response.ok) {
            alert("댓글을 등록하지 못했습니다. 내용을 확인해주세요.");  // 사용자에게 실패했다고 알려줌
            return;  // 여기서 함수 실행을 끝냄 (아래에 있는, 화면에 댓글 추가하는 코드는 실행 안 됨)
        }
        const comment = await response.json();  // 서버가 만들어준 댓글 정보(작성자, 내용, id 등)를 받음

        const list = section.querySelector(".comment-list");  // 이 게시물의 댓글 목록(ul)을 찾음
        const item = document.createElement("li");             // 새 댓글을 담을 <li> 태그를 하나 만듦
        item.className = "comment-list__item";                 // CSS가 먹도록 클래스 이름을 붙여줌
        item.dataset.commentId = comment.id;                    // 서버 렌더링 버전과 동일하게 댓글 id를 심어둠 (수정/삭제 버튼이 찾을 수 있도록)

        // 서버가 렌더링하는 것과 똑같은 구조로 내부를 채움: 작성자, 내용, 수정/삭제 버튼
        item.innerHTML = `
            <strong>${comment.user}</strong>
            <span class="comment-list__content">${comment.content}</span>
            <button class="comment-edit-button">수정</button>
            <button class="comment-delete-button">삭제</button>
        `;

        list.appendChild(item);  // 만든 <li>를 목록 맨 끝에 실제로 붙임

        // 방금 만든 수정/삭제 버튼에도, 1~2단계에서 만든 함수를 그대로 재사용해서 이벤트를 걸어줌
        attachDeleteHandler(item.querySelector(".comment-delete-button"));
        attachEditHandler(item.querySelector(".comment-edit-button"));
        input.value = "";  // 등록 후 입력창을 다시 빈 칸으로 비움
    });
});

// 삭제 버튼 "하나"에 클릭 이벤트를 걸어주는 함수. 기존 버튼이든 새로 만든 버튼이든 이 함수 하나로 재사용함
function attachDeleteHandler(button) {
    button.addEventListener("click", async () => {
        const item = button.closest(".comment-list__item");  // 이 버튼이 속한 댓글 <li>를 찾음
        const commentId = item.dataset.commentId;              // 그 <li>에 심어둔 댓글 id
        const postId = button.closest(".comment-section").dataset.postId;  // 이 댓글이 속한 게시물 id

        const confirmed = confirm("댓글을 삭제하시겠습니까?");  // 브라우저 기본 확인창 (확인/취소 버튼)
        if (!confirmed) {
            return;  // "취소"를 누르면 여기서 함수를 끝내고 아무 일도 안 일어남
        }

        // 서버의 댓글 삭제 API로 DELETE 요청을 보냄
        const response = await fetch(`/api/posts/${postId}/comments/${commentId}/`, {
            method: "DELETE",
            headers: {
                "X-CSRFToken": csrftoken,  // 지금까지와 같은 CSRF 토큰
            },
        });

        if (!response.ok) {
            alert("댓글을 삭제하지 못했습니다.");  // 실패 시 알림
            return;
        }

        item.remove();  // 성공했으면 화면에서 이 댓글 <li>를 통째로 없앰
    });
}
document.querySelectorAll(".comment-delete-button").forEach(attachDeleteHandler);

// 수정 버튼 "하나"에 클릭 이벤트를 걸어주는 함수. 기존 버튼이든 새로 만든 버튼이든 이 함수 하나로 재사용함
function attachEditHandler(button) {
    button.addEventListener("click", async () => {
        const item = button.closest(".comment-list__item");           // 이 버튼이 속한 댓글 <li>
        const content = item.querySelector(".comment-list__content"); // 댓글 텍스트가 담긴 span

        if (button.textContent === "수정") {
            // 지금 "수정" 상태라면 → 텍스트를 입력창으로 바꿔주는 모드
            const input = document.createElement("input");  // 수정용 입력창을 새로 만듦
            input.type = "text";
            input.className = "comment-edit-input";          // CSS 스타일 적용용 클래스
            input.value = content.textContent;                // 지금 댓글 내용을 입력창 기본값으로 채움
            content.replaceWith(input);  // 화면에서 텍스트(span)를 입력창으로 통째로 바꿔치기
            input.focus();                // 바로 타이핑할 수 있게 입력창에 커서를 놓음

            button.textContent = "저장"; // 문구를 "수정"에서 "저장"으로 바꿈
        } else {
            // 지금 "저장" 상태라면 → 입력창 내용을 서버에 실제로 반영하는 모드
            const input = item.querySelector(".comment-edit-input");  // 방금 만들어둔 입력창을 찾음
            const commentId = item.dataset.commentId;                  // 이 댓글의 id
            const postId = button.closest(".comment-section").dataset.postId;  // 이 댓글이 속한 게시물 id

            // 서버의 댓글 수정 API로 PATCH 요청을 보냄
            const response = await fetch(`/api/posts/${postId}/comments/${commentId}/`, {
                method: "PATCH",
                headers: {
                    "X-CSRFToken": csrftoken,
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ content: input.value }),  // 입력창에 지금 쓰여있는 값을 보냄
            });

            if (!response.ok) {
                alert("댓글을 수정하지 못했습니다.");
                return;
            }

            const comment = await response.json();  // 서버가 돌려준, 수정 완료된 댓글 정보

            const newContent = document.createElement("span");   // 다시 보여줄 텍스트용 span을 새로 만듦
            newContent.className = "comment-list__content";
            newContent.textContent = comment.content;              // 서버가 확정해준 최신 내용으로 채움

            input.replaceWith(newContent);  // 입력창을 다시 텍스트(span)로 바꿔치기
            button.textContent = "수정";     // 버튼 문구를 다시 "수정"으로 되돌림
        }
    });
}

// class="comment-edit-button"인 버튼을 전부 찾아서, 각각에 위 함수로 이벤트를 걸어줌
document.querySelectorAll(".comment-edit-button").forEach(attachEditHandler);