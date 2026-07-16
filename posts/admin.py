from django.contrib import admin

from .models import Post, Comment, Like


class PostAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "caption", "like_count", "created_at"]  # 목록 화면에 보여줄 컬럼들

    def like_count(self, obj):
        # obj = 목록의 각 Post 한 줄(row). likes는 Like 모델의 related_name이라, obj.likes는 "이 Post를 좋아요한 Like들"
        return obj.likes.count()  # 그 개수만 세서 반환

    like_count.short_description = "좋아요 수"  # 컬럼 제목을 "like_count" 대신 한글로 표시


admin.site.register(Post, PostAdmin)  # 기본 등록 대신, 방금 만든 PostAdmin으로 등록
admin.site.register(Comment)
admin.site.register(Like)
