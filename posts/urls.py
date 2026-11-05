from django.urls import path

from . import views

app_name = "posts"  # base.html에서 썼던 {% url 'posts:feed' %}의 "posts" 부분

urlpatterns = [
    path("", views.feed, name="feed"),  # 루트 경로("/")를 feed 뷰에 연결
    path("posts/<int:post_id>/", views.post_detail, name="detail"),  # "/posts/5/" 같은 주소를 post_detail 뷰로 연결, {% url %}에서는 "posts:detail"로 참조
    path("api/posts/", views.PostListCreateAPIView.as_view(), name="post-list-api"),
    path("api/posts/<int:post_id>/comments/", views.CommentListCreateAPIView.as_view(), name="comment-list-api"),
    path("api/posts/<int:post_id>/comments/<int:comment_id>/", views.CommentDetailAPIView.as_view(), name="comment-detail-api"),
    path("api/posts/<int:post_id>/like/", views.LikeToggleAPIView.as_view(), name="like-toggle-api"),
]
