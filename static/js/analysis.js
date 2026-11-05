// "분석 중" 상태일 때 화면에 있는 폴링 영역 하나에 주기적 상태 확인을 걸어주는 함수
function attachAnalysisPolling(container) {
    const statusUrl = container.dataset.statusUrl;  // HTML에 심어둔 상태 조회 API 주소 (data-status-url)

    const checkStatus = async () => {                   // 상태 한 번 확인하는 동작을 별도 함수로 뽑아냄
        const response = await fetch(statusUrl);        // GET 요청 (조회만 하니까 CSRF 토큰 필요 없음)
        const data = await response.json();              // {"status": "pending"} 같은 형태로 응답 옴

        if (data.status === "completed" || data.status === "failed") {
            clearInterval(intervalId);                       // 끝났으니 더 이상 반복 확인할 필요 없음
            location.reload();                                 // 페이지를 다시 불러와서 완료된 결과를 보여줌
        }
    };

    checkStatus();                                       // 페이지 뜨자마자 바로 한 번 확인 (3초 안 기다림)
    const intervalId = setInterval(checkStatus, 3000);   // 그 이후부터는 3초마다 반복 확인
}

// class="analysis-polling"인 영역을 전부 찾아서 폴링 시작 (분석 중일 때만 템플릿에서 렌더링됨)
document.querySelectorAll(".analysis-polling").forEach(attachAnalysisPolling);