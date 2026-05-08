import json

from django.http import Http404
from django.utils.safestring import mark_safe
from django.views.generic import TemplateView
from rest_framework.views import APIView
from rest_framework.response import Response

from .services import get_all_problems, get_problem_by_id, get_problems_grouped
from .serializers import ProblemSummarySerializer, ProblemDetailSerializer


class HomeView(TemplateView):
    template_name = "problems/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        grouped = get_problems_grouped()
        ctx["grouped"] = grouped
        ctx["grouped_json"] = mark_safe(json.dumps(grouped))
        return ctx


class ProblemDetailTemplateView(TemplateView):
    template_name = "problems/detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        problem = get_problem_by_id(self.kwargs["pk"])
        if not problem:
            raise Http404("Problem not found")
        ctx["problem"] = problem
        ctx["instruction_json"]  = mark_safe(json.dumps(problem["instruction"]))
        ctx["stub_files_json"]   = mark_safe(json.dumps(problem.get("stub_files", [])))
        ctx["problem_meta_json"] = mark_safe(json.dumps({
            "task_name": f"{problem['dataset']}/{problem['name']}",
            "dataset":   problem["dataset"],
        }))
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
