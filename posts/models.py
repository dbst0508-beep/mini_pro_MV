from django.conf import settings
from django.db import models


class Post(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="posts",
    )
    image = models.ImageField(upload_to="posts/")
    caption = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} - {self.created_at:%Y-%m-%d}"

class Comment(models.Model):
    # 이 댓글이 어느 게시물에 달린 것인지 연결 (N:1 관계)
    post = models.ForeignKey(
        Post,  # 같은 파일에 있는 Post 클래스를 바로 참조 (import 불필요)
        on_delete=models.CASCADE,  # 게시물이 삭제되면 그 댓글들도 같이 삭제
        related_name="comments",  # post.comments.all()로 역방향 조회 가능하게 이름 지정
    )
    # 이 댓글을 누가 작성했는지 연결
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,  # accounts.User를 문자열로 참조 (직접 import 안 함)
        on_delete=models.CASCADE,  # 유저가 삭제되면 그 유저가 쓴 댓글도 같이 삭제
        related_name="comments",  # user.comments.all()로 역방향 조회 가능하게 이름 지정
    )
    content = models.TextField()  # 댓글 본문 텍스트, 길이 제한 없음
    created_at = models.DateTimeField(auto_now_add=True)  # 작성 시각, 생성 시 한 번만 자동 기록

    def __str__(self):
        # admin/shell에서 이 객체를 출력할 때 "작성자 - 댓글앞부분" 형태로 보여줌
        return f"{self.user} - {self.content[:20]}"
    
class Like(models.Model):
    # 어느 게시물에 좋아요를 눌렀는지 연결
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,  # 게시물 삭제되면 그 좋아요 기록도 같이 삭제
        related_name="likes",  # post.likes.all() / post.likes.count()로 조회
    )
    # 누가 눌렀는지 연결
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,  # 유저 삭제되면 그 유저가 누른 좋아요도 같이 삭제
        related_name="likes",  # user.likes.all()로 조회
    )
    created_at = models.DateTimeField(auto_now_add=True)  # 누른 시각

    class Meta:
        # 같은 (post, user) 조합이 두 번 생기지 못하게 DB 레벨에서 막음
        unique_together = ("post", "user")

    def __str__(self):
        return f"{self.user} likes {self.post}"

