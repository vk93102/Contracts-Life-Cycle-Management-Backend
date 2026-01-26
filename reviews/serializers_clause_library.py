from rest_framework import serializers
from .models import ClauseLibraryItem


class ClauseLibraryItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClauseLibraryItem
        fields = [
            'id',
            'key',
            'category',
            'title',
            'content',
            'default_risk',
            'created_at',
            'updated_at',
        ]
