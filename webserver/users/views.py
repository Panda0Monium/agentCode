from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View

from .forms import ModelConfigForm


@method_decorator(login_required, name='dispatch')
class ModelConfigView(View):
    template_name = 'users/model_config.html'

    def get(self, request):
        return render(request, self.template_name, {'form': ModelConfigForm(instance=request.user)})

    def post(self, request):
        form = ModelConfigForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            return redirect('model_config')
        return render(request, self.template_name, {'form': form})
