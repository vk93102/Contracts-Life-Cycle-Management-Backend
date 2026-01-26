from rest_framework import serializers
from .models import ReviewContract


class ReviewContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewContract
        fields = [
            'id',
            'title',
            'original_filename',
            'file_type',
            'size_bytes',
            'status',
            'created_at',
            'updated_at',
        ]


class ReviewContractDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewContract
        fields = [
            'id',
            'title',
            'original_filename',
            'file_type',
            'size_bytes',
            'r2_key',
            'status',
            'error_message',
            'analysis',
            'review_text',
            'created_at',
            'updated_at',
        ]


class ReviewContractCreateSerializer(serializers.Serializer):
    title = serializers.CharField(required=False, allow_blank=True)
    analyze = serializers.BooleanField(required=False, default=True)
