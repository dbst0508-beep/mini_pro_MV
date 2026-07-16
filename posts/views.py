from django.shortcuts import render , get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import Post, Comment, Like

from rest_framework import generics, permissions

from .serializers import PostSerializer, CommentSerializer
from django.db.models import Count

def feed(request):
    posts = Post.objects.select_related("user").annotate(like_count=Count("likes")).order_by("-created_at")

    # 로그인한 사용자가 좋아요 누른 게시물 id들만 모음 (예: {1, 3, 5})
    if request.user.is_authenticated:
        liked_post_ids = set(
            Like.objects.filter(user=request.user).values_list("post_id", flat=True)
        )
    else:
        liked_post_ids = set()  # 로그인 안 했으면 좋아요 누른 게 있을 수 없음

    # 게시물 하나하나에 "내가 좋아요 눌렀는지" 표시를 임시로 붙여줌
    for post in posts:
        post.is_liked = post.id in liked_post_ids

    return render(request, "posts/feed.html", {"posts": posts})


class PostListCreateAPIView(generics.ListCreateAPIView):
    queryset = Post.objects.select_related("user").order_by("-created_at")
    serializer_class = PostSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)  # 로그인한 유저를 작성자로 자동 지정

class CommentListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        # URL의 <post_id>에 해당하는 게시물의 댓글만 걸러서 보여줌
        return Comment.objects.filter(post_id=self.kwargs["post_id"]).select_related("user")

    def perform_create(self, serializer):
        # URL의 post_id로 실제 Post 객체를 찾음 (없으면 자동으로 404 응답)
        post = get_object_or_404(Post, pk=self.kwargs["post_id"])
        serializer.save(user=self.request.user, post=post)
        
class LikeToggleAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]  # 좋아요는 로그인 필수, 조회 개념이 없음

    def post(self, request, post_id):
        post = get_object_or_404(Post, pk=post_id)
        like, created = Like.objects.get_or_create(post=post, user=request.user)

        if created:
            response_status = status.HTTP_201_CREATED
        else:
            like.delete()
            response_status = status.HTTP_200_OK

        # 응답에 liked 여부뿐 아니라 최신 좋아요 개수도 같이 실어 보냄
        return Response(
            {"liked": created, "like_count": post.likes.count()},
            status=response_status,
    )

    
