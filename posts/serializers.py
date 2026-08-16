from rest_framework import serializers
from .models import Comment
from .models import Post


class PostSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)  # 조회 시 유저 정보는 이름만, 수정 불가

    class Meta:
        model = Post
        fields = ["id", "user", "image", "caption", "created_at"]
        read_only_fields = ["id", "user", "created_at"]

class CommentSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)  # PostSerializer와 동일한 패턴

    class Meta:
        model = Comment
        fields = ["id", "user", "content", "created_at"]
        read_only_fields = ["id", "user", "created_at"]