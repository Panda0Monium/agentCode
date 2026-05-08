from rest_framework import serializers


class ProblemSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    display_name = serializers.CharField()
    difficulty = serializers.CharField()
    language = serializers.CharField()
    short_description = serializers.CharField()
    dataset = serializers.CharField()


class ProblemDetailSerializer(ProblemSummarySerializer):
    instruction = serializers.CharField()
    timeout_sec = serializers.IntegerField()
