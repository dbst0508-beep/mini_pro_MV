from django.shortcuts import render , get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status


from .models import Post, Comment, Like

from rest_framework import generics, permissions

from .serializers import PostSerializer, CommentSerializer
from django.db.models import Count

from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer, OpenApiResponse  # Swagger 문서에 설명을 덧붙이는 도구들
from rest_framework import serializers                                # inline_serializer로 응답 모양을 만들 때 필드 타입을 쓰기 위해 불러옴

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

    
    latest_analysis = post.analyses.order_by("-created_at").first()  # 이 게시물의 가장 최근 분석 기록 (없으면 None)
    if request.user.is_authenticated:  # feed()와 동일하게, 로그인 여부로 분기
        post.is_liked = Like.objects.filter(post=post, user=request.user).exists()
        # 이 게시물에 대해 (post, 현재유저) 조합의 Like가 존재하는지 True/False로 확인
    else:
        post.is_liked = False  # 로그인 안 한 사람은 좋아요를 누른 적이 있을 수 없음

    return render(request, "posts/detail.html", {"post": post, "latest_analysis": latest_analysis})

@extend_schema_view(                                                  # 이 클래스의 메서드(GET/POST)마다 Swagger 설명을 따로 붙이는 데코레이터
    get=extend_schema(tags=["게시물"], summary="게시물 목록 조회"),           # GET 요청: "게시물" 그룹에 묶고, 한 줄 설명 표시
    post=extend_schema(tags=["게시물"], summary="게시물 작성 (로그인 필요)", request={"multipart/form-data": PostSerializer}),  # POST 요청 본문을 파일 업로드(multipart) 형식으로만 문서화 → Swagger에 파일 선택 버튼이 나옴
)


class PostListCreateAPIView(generics.ListCreateAPIView):
    queryset = Post.objects.select_related("user").order_by("-created_at")
    serializer_class = PostSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)  # 로그인한 유저를 작성자로 자동 지정

@extend_schema_view(                                                  # 댓글 목록/작성용 설명
    get=extend_schema(tags=["댓글"], summary="댓글 목록 조회"),               # GET 요청: "댓글" 그룹
    post=extend_schema(tags=["댓글"], summary="댓글 작성 (로그인 필요)"),      # POST 요청: 로그인 필요
)


class CommentListCreateAPIView(generics.ListCreateAPIView):
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        # URL의 <post_id>에 해당하는 게시물의 댓글만 걸러서 보여줌
        if getattr(self, "swagger_fake_view", False):                  # 지금 요청이 아니라 "Swagger 문서를 만드는 중"이면 (drf-spectacular가 이 속성을 True로 켜 둠)
            return Comment.objects.none()                              # 실제 post_id가 없으니 빈 결과를 돌려줘서 self.kwargs["post_id"] 에러를 피함

        return Comment.objects.filter(post_id=self.kwargs["post_id"]).select_related("user")

    def perform_create(self, serializer):
        # URL의 post_id로 실제 Post 객체를 찾음 (없으면 자동으로 404 응답)
        post = get_object_or_404(Post, pk=self.kwargs["post_id"])
        serializer.save(user=self.request.user, post=post)

@extend_schema_view(                                                  # 댓글 단건용 설명 (조회/수정/삭제)
    get=extend_schema(tags=["댓글"], summary="댓글 단건 조회"),                  # GET 요청
    put=extend_schema(tags=["댓글"], summary="댓글 전체 수정 (작성자만)"),         # PUT 요청: 모든 필드를 보내서 수정
    patch=extend_schema(tags=["댓글"], summary="댓글 부분 수정 (작성자만)"),       # PATCH 요청: 바꿀 필드만 보내서 수정
    delete=extend_schema(tags=["댓글"], summary="댓글 삭제 (작성자만)"),          # DELETE 요청
)


class CommentDetailAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CommentSerializer  # 응답/수정에 CommentSerializer(id, user, content, created_at) 그대로 사용
    permission_classes = [IsOwnerOrReadOnly]  # 1단계에서 만든 규칙: 조회는 누구나, 수정/삭제는 작성자만
    lookup_url_kwarg = "comment_id"  # URL에서 어떤 이름의 값으로 댓글을 찾을지 지정 (기본값 "pk" 대신 "comment_id" 사용)
    def get_queryset(self):                                            # 이 API가 다룰 댓글의 범위를 정하는 함수 (DRF가 요청마다 호출)
        if getattr(self, "swagger_fake_view", False):                  # Swagger 문서를 만드는 중이면 (실제 post_id가 없는 상황)
            return Comment.objects.none()                              # 빈 결과를 돌려줘서 self.kwargs["post_id"] 에러를 피함
        return Comment.objects.filter(post_id=self.kwargs["post_id"]).select_related("user")  # URL의 post_id에 속한 댓글만 대상으로 삼음. 다른 게시물의 댓글이면 못 찾아서 404
LikeToggleResponseSerializer = inline_serializer(                     # serializer 파일을 따로 만들지 않고 응답 모양만 문서용으로 즉석에서 정의
    name="LikeToggleResponse",                                        # Swagger 화면에 표시될 응답 모양의 이름
    fields={                                                          # 응답 JSON에 들어 있는 항목들
        "liked": serializers.BooleanField(),                          # 좋아요가 눌린 상태인지 (true/false)
        "like_count": serializers.IntegerField(),                     # 현재 이 게시물의 좋아요 총 개수
    },
)

class LikeToggleAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]  # 좋아요는 로그인 필수, 조회 개념이 없음
    @extend_schema(                                                   # 이 POST 메서드의 Swagger 설명
        tags=["좋아요"],                                               # "좋아요" 그룹에 묶음
        summary="좋아요 토글 (로그인 필요)",                              # 한 줄 설명: 누르면 추가, 다시 누르면 취소
        request=None,                                                 # 요청 본문이 없음 (URL의 post_id만 사용)
        responses={                                                   # 상태 코드별 응답 설명
            201: OpenApiResponse(response=LikeToggleResponseSerializer, description="좋아요가 추가됨"),   # 새로 눌렀을 때
            200: OpenApiResponse(response=LikeToggleResponseSerializer, description="좋아요가 취소됨"),   # 이미 눌러서 취소됐을 때
        },
    )

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

    
