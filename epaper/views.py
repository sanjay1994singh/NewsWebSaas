from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from tenants.models import Tenant

from .forms import EPaperEditionForm
from .models import EPaperEdition
from .services import can_upload_epaper, epaper_limit_reached, mark_epaper_ready


def _owned_tenant(user):
    return Tenant.objects.filter(owner=user).first()


def public_epaper_home(request, tenant_slug):
    tenant = get_object_or_404(Tenant, slug=tenant_slug)
    editions = EPaperEdition.objects.filter(tenant=tenant, status=EPaperEdition.Status.PUBLISHED)
    if request.GET.get('city'):
        editions = editions.filter(city=request.GET['city'])
    if request.GET.get('date'):
        editions = editions.filter(publication_date=request.GET['date'])
    return render(request, 'epaper/home.html', {'tenant': tenant, 'editions': editions})


def epaper_reader(request, tenant_slug, slug):
    tenant = get_object_or_404(Tenant, slug=tenant_slug)
    edition = get_object_or_404(EPaperEdition, tenant=tenant, slug=slug, status=EPaperEdition.Status.PUBLISHED)
    return render(request, 'epaper/reader.html', {'tenant': tenant, 'edition': edition})


@login_required
def dashboard(request):
    tenant = _owned_tenant(request.user)
    if tenant is None:
        return JsonResponse({'detail': 'No tenant workspace found.'}, status=404)
    editions = EPaperEdition.objects.filter(tenant=tenant)
    return render(request, 'epaper/dashboard.html', {'tenant': tenant, 'editions': editions, 'can_upload': can_upload_epaper(tenant)})


@login_required
def create_edition(request):
    tenant = _owned_tenant(request.user)
    if tenant is None:
        return JsonResponse({'detail': 'No tenant workspace found.'}, status=404)
    if not can_upload_epaper(tenant) or epaper_limit_reached(tenant):
        return JsonResponse({'detail': 'E-Paper upload is not enabled for this tenant.'}, status=403)
    if request.method == 'POST':
        form = EPaperEditionForm(request.POST, request.FILES)
        if form.is_valid():
            edition = form.save(commit=False)
            edition.tenant = tenant
            edition.created_by = request.user
            edition.status = EPaperEdition.Status.PROCESSING
            edition.save()
            mark_epaper_ready(edition)
            messages.success(request, 'E-Paper edition uploaded and queued for processing.')
            return redirect('epaper:dashboard')
    else:
        form = EPaperEditionForm()
    return render(request, 'epaper/form.html', {'form': form, 'tenant': tenant})


@login_required
@require_POST
def publish_edition(request, edition_id):
    tenant = _owned_tenant(request.user)
    edition = get_object_or_404(EPaperEdition, pk=edition_id, tenant=tenant)
    if not can_upload_epaper(tenant):
        return JsonResponse({'detail': 'E-Paper publishing is not enabled for this tenant.'}, status=403)
    edition.status = EPaperEdition.Status.PUBLISHED
    edition.published_at = timezone.now()
    edition.save(update_fields=['status', 'published_at', 'updated_at'])
    messages.success(request, 'E-Paper edition published.')
    return redirect('epaper:dashboard')


def download_edition(request, tenant_slug, slug):
    tenant = get_object_or_404(Tenant, slug=tenant_slug)
    edition = get_object_or_404(EPaperEdition, tenant=tenant, slug=slug, status=EPaperEdition.Status.PUBLISHED, allow_download=True)
    return FileResponse(edition.pdf_file.open('rb'), as_attachment=True, filename=edition.pdf_file.name.rsplit('/', 1)[-1])
