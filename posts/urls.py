from django.urls import path

from . import views

app_name = "posts"  # base.html에서 썼던 {% url 'posts:feed' %}의 "posts" 부분

urlpatterns = [
    path("", views.feed, name="feed"),  # 루트 경로("/")를 feed 뷰에 연결
    path("api/posts/", views.PostListCreateAPIView.as_view(), name="post-list-api"),
    path("api/posts/<int:post_id>/comments/", views.CommentListCreateAPIView.as_view(), name="comment-list-api"),
    path("api/posts/<int:post_id>/like/", views.LikeToggleAPIView.as_view(), name="like-toggle-api"),
]
