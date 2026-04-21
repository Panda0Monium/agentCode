from django.views.generic import TemplateView
from rest_framework.views import APIView
from rest_framework.response import Response

from .services import get_all_problems, get_problem_by_id
from .serializers import ProblemSummarySerializer, ProblemDetailSerializer


class HomeView(TemplateView):
    template_name = "problems/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["problems"] = get_all_problems()
        return ctx


class ProblemListView(APIView):
    def get(self, request):
        return Response(ProblemSummarySerializer(get_all_problems(), many=True).data)


class ProblemDetailView(APIView):
    def get(self, request, pk):
        problem = get_problem_by_id(pk)
        if not problem:
            return Response(status=404)
        return Response(ProblemDetailSerializer(problem).data)
