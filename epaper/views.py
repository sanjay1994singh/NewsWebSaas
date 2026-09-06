from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from tenants.models import Tenant

from .forms import EPaperEditionForm
from .models import EPaperEdition
from .services import can_upload_epaper, epaper_limit_reached, mark_epaper_ready


def _owned_tenant(user):
    return Tenant.objects.filter(owner=user).first()


def _public_tenant(request, tenant_slug=None):
    domain_tenant = getattr(request, 'tenant', None)
    if domain_tenant is not None:
        if tenant_slug and tenant_slug != domain_tenant.slug:
            raise Http404('Publication not found.')
        tenant = domain_tenant
    elif tenant_slug:
        tenant = get_object_or_404(Tenant, slug=tenant_slug, status__in=['trial', 'active', 'past_due'])
    else:
        raise Http404('Publication not found.')
    if not can_upload_epaper(tenant):
        raise Http404('E-Paper is not available.')
    return tenant


def public_epaper_home(request, tenant_slug=None):
    tenant = _public_tenant(request, tenant_slug)
    editions = EPaperEdition.objects.filter(tenant=tenant, status=EPaperEdition.Status.PUBLISHED)
    if request.GET.get('city'):
        editions = editions.filter(city=request.GET['city'])
    if request.GET.get('date'):
        editions = editions.filter(publication_date=request.GET['date'])
    return render(request, 'epaper/home.html', {'tenant': tenant, 'editions': editions, 'domain_reader': tenant_slug is None})


def epaper_reader(request, slug, tenant_slug=None):
    tenant = _public_tenant(request, tenant_slug)
    edition = get_object_or_404(EPaperEdition, tenant=tenant, slug=slug, status=EPaperEdition.Status.PUBLISHED)
    return render(request, 'epaper/reader.html', {'tenant': tenant, 'edition': edition, 'domain_reader': tenant_slug is None})


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
        form = EPaperEditionForm(request.POST, request.FILES, tenant=tenant, user=request.user)
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
        form = EPaperEditionForm(tenant=tenant, user=request.user)
    return render(request, 'epaper/form.html', {'form': form, 'tenant': tenant})


@login_required
@require_POST
def publish_edition(request, edition_id):
    tenant = _owned_tenant(request.user)
    edition = get_object_or_404(EPaperEdition, uuid=edition_id, tenant=tenant)
    if not can_upload_epaper(tenant):
        return JsonResponse({'detail': 'E-Paper publishing is not enabled for this tenant.'}, status=403)
    edition.status = EPaperEdition.Status.PUBLISHED
    edition.published_at = timezone.now()
    edition.save(update_fields=['status', 'published_at', 'updated_at'])
    messages.success(request, 'E-Paper edition published.')
    return redirect('epaper:dashboard')


def download_edition(request, slug, tenant_slug=None):
    tenant = _public_tenant(request, tenant_slug)
    edition = get_object_or_404(EPaperEdition, tenant=tenant, slug=slug, status=EPaperEdition.Status.PUBLISHED, allow_download=True)
    return FileResponse(edition.pdf_file.open('rb'), as_attachment=True, filename=edition.pdf_file.name.rsplit('/', 1)[-1])
