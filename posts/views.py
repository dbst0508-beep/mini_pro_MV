from django.shortcuts import render , get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import Post, Comment, Like

from rest_framework import generics, permissions

from .serializers import PostSerializer, CommentSerializer
from django.db.models import Count

class IsOwnerOrReadOnly(permissions.BasePermission):
    # DRF가 API 요청마다 자동으로 호출해서, 이 요청을 허용할지 판단하는 함수
    def has_object_permission(self, request, view, obj):
        # GET처럼 "그냥 읽기만 하는" 요청은 누구나 허용 (permissions.SAFE_METHODS = GET, HEAD, OPTIONS)
        if request.method in permissions.SAFE_METHODS:
            return True
        # 그 외(PATCH, DELETE 같은 "수정하는" 요청)는, 이 댓글의 작성자와 요청한 사람이 같을 때만 허용
        return obj.user == request.user

def feed(request):
    posts = Post.objects.select_related("user").prefetch_related("comments__user").annotate(like_count=Count("likes")).order_by("-created_at")
# select_related("user")            : 게시물 작성자 정보를 JOIN으로 한 번에 가져옴 (1:1 관계에 사용)
# .prefetch_related("comments__user") : 이번에 추가한 부분. 각 게시물의 댓글들 + 그 댓글 작성자까지 미리 가져옴
# .annotate(like_count=Count("likes")) : 게시물마다 좋아요 개수를 미리 계산해서 붙여줌
# .order_by("-created_at")           : 최신 게시물이 위로 오도록 정렬

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

def post_detail(request, post_id):  # URL의 <int:post_id> 부분 값이 post_id 인자로 그대로 들어옴
    post = get_object_or_404(  # 조건에 맞는 게시물이 없으면 자동으로 404 Not Found 페이지를 보여줌
        Post.objects.select_related("user").prefetch_related("comments__user").annotate(like_count=Count("likes")),
        # feed()에서 썼던 것과 똑같은 쿼리: 작성자/댓글작성자/좋아요개수를 미리 다 가져와서 붙여둠
        pk=post_id,  # Post 테이블에서 기본키(pk)가 post_id와 같은 행 하나를 찾으라는 조건
    )

    if request.user.is_authenticated:  # feed()와 동일하게, 로그인 여부로 분기
        post.is_liked = Like.objects.filter(post=post, user=request.user).exists()
        # 이 게시물에 대해 (post, 현재유저) 조합의 Like가 존재하는지 True/False로 확인
    else:
        post.is_liked = False  # 로그인 안 한 사람은 좋아요를 누른 적이 있을 수 없음

    return render(request, "posts/detail.html", {"post": post})  # posts 리스트가 아니라 post 하나만 템플릿에 넘김

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

class CommentDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Comment.objects.select_related("user")  # 조회 대상이 될 댓글 전체 (특정 댓글 하나를 여기서 찾아냄)
    serializer_class = CommentSerializer  # 응답/수정에 CommentSerializer(id, user, content, created_at) 그대로 사용
    permission_classes = [IsOwnerOrReadOnly]  # 1단계에서 만든 규칙: 조회는 누구나, 수정/삭제는 작성자만
    lookup_url_kwarg = "comment_id"  # URL에서 어떤 이름의 값으로 댓글을 찾을지 지정 (기본값 "pk" 대신 "comment_id" 사용)


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

    
