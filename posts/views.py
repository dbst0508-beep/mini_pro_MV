from django.shortcuts import render

from .models import Post


def feed(request):
    # DB에서 모든 게시물을 최신순으로 가져옴
    posts = Post.objects.select_related("user").order_by("-created_at")
    # posts.html에 posts라는 이름으로 데이터를 넘겨서 렌더링
    return render(request, "posts/feed.html", {"posts": posts})
