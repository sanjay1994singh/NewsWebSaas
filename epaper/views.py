from django.contrib import messages

from django.contrib.auth.decorators import login_required

from django.http import FileResponse, Http404, JsonResponse

from django.shortcuts import get_object_or_404, redirect, render

from django.utils import timezone

from django.views.decorators.http import require_POST



from tenants.models import Tenant



from .forms import EPaperEditionForm

from .models import EPaperEdition

from .services import processing_progress, can_upload_epaper, epaper_limit_reached





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





def _reader_context(request, tenant, edition, tenant_slug=None, filter_error=''):

    from django.urls import reverse

    domain = tenant_slug is None

    home_url = reverse('epaper:domain_home') if domain else reverse('epaper:public_home', args=[tenant.slug])

    published = EPaperEdition.objects.filter(tenant=tenant, status=EPaperEdition.Status.PUBLISHED)

    pages = []

    if edition:

        pages = [{'number': p.number, 'image': p.image.url, 'mobile': p.mobile_image.url,

                  'zoom': p.zoom_image.url, 'thumbnail': p.thumbnail.url,

                  'width': p.width, 'height': p.height} for p in edition.pages.all()]

    try:

        index = max(0, min(int(request.GET.get('page', 1)) - 1, len(pages) - 1))

    except (ValueError, TypeError):

        index = 0

    edition_url = (reverse('epaper:domain_reader', args=[edition.slug]) if domain else reverse('epaper:reader', args=[tenant.slug, edition.slug])) if edition else home_url

    context = {

        'tenant': tenant, 'edition': edition, 'pages': pages, 'initial_page': pages[index] if pages else None,

        'initial_index': index, 'reader_home_url': home_url, 'edition_url': edition_url,

        'site_home_url': '/' if domain else f'/site/{tenant.slug}/',

        'domain_reader': domain, 'filter_error': filter_error,

        'cities': published.exclude(city='').order_by('city').values_list('city', flat=True).distinct(),

        'edition_names': published.exclude(edition_name='').order_by('edition_name').values_list('edition_name', flat=True).distinct(),

        'selected_city': request.GET.get('city', edition.city if edition else ''),

        'selected_name': request.GET.get('edition', edition.edition_name if edition else ''),

        'selected_date': request.GET.get('date', edition.publication_date.isoformat() if edition else ''),

        'bookmark_key': f'epaper:{tenant.pk}:{edition.uuid}' if edition else '',

        'share_url': request.build_absolute_uri(edition_url),

    }

    return render(request, 'epaper/reader.html', context)





def public_epaper_home(request, tenant_slug=None):

    from django.utils.dateparse import parse_date

    tenant = _public_tenant(request, tenant_slug)

    editions = EPaperEdition.objects.filter(tenant=tenant, status=EPaperEdition.Status.PUBLISHED)

    if request.GET.get('city'):

        editions = editions.filter(city=request.GET['city'])

    if request.GET.get('edition'):

        editions = editions.filter(edition_name=request.GET['edition'])

    if request.GET.get('date'):

        try:

            selected_date = parse_date(request.GET['date'])

        except ValueError:

            selected_date = None

        if selected_date is None:

            return _reader_context(request, tenant, None, tenant_slug, 'Please choose a valid date.')

        editions = editions.filter(publication_date=selected_date)

    return _reader_context(request, tenant, editions.first(), tenant_slug)





def epaper_reader(request, slug, tenant_slug=None):

    tenant = _public_tenant(request, tenant_slug)

    edition = get_object_or_404(EPaperEdition, tenant=tenant, slug=slug, status=EPaperEdition.Status.PUBLISHED)

    return _reader_context(request, tenant, edition, tenant_slug)





@login_required

def dashboard(request):

    tenant = _owned_tenant(request.user)

    if tenant is None:

        return JsonResponse({'detail': 'No tenant workspace found.'}, status=404)

    editions = list(EPaperEdition.objects.filter(tenant=tenant))

    for edition in editions:

        edition.progress = processing_progress(edition)

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

            messages.success(request, 'PDF uploaded. Pages are being prepared; publish the edition when its status is Ready.')

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

    if edition.status != EPaperEdition.Status.READY or not edition.pages.exists():

        messages.error(request, 'Prepare all pages before publishing this edition.')

        return redirect('epaper:dashboard')

    edition.status = EPaperEdition.Status.PUBLISHED

    edition.published_at = timezone.now()

    edition.save(update_fields=['status', 'published_at', 'updated_at'])

    messages.success(request, 'E-Paper edition published.')

    return redirect('epaper:dashboard')





def download_edition(request, slug, tenant_slug=None):

    tenant = _public_tenant(request, tenant_slug)

    edition = get_object_or_404(EPaperEdition, tenant=tenant, slug=slug, status=EPaperEdition.Status.PUBLISHED, allow_download=True)

    return FileResponse(edition.pdf_file.open('rb'), as_attachment=True, filename=edition.pdf_file.name.rsplit('/', 1)[-1])





@login_required

def processing_status(request):

    tenant = _owned_tenant(request.user)

    if tenant is None:

        return JsonResponse({'detail': 'No workspace found.'}, status=404)

    from uuid import UUID
    try:
        ids = [UUID(value) for value in request.GET.getlist('id')[:100]]
    except ValueError:
        return JsonResponse({'detail': 'Invalid edition ID.'}, status=400)
    editions = EPaperEdition.objects.filter(tenant=tenant, uuid__in=ids)

    response = JsonResponse({'editions': [processing_progress(item) for item in editions]})

    response['Cache-Control'] = 'no-store'

    return response


@login_required
@require_POST
def delete_edition(request, edition_id):
    from django.db import transaction
    tenant = _owned_tenant(request.user)
    if tenant is None:
        raise Http404('Publication not found.')
    with transaction.atomic():
        edition = get_object_or_404(EPaperEdition.objects.select_for_update(), uuid=edition_id, tenant=tenant)
        if edition.processing_token:
            messages.error(request, 'This edition is being processed. Please delete it after processing finishes. If processing has stopped, contact support.')
            return redirect('epaper:dashboard')
        edition.delete()
    messages.success(request, 'E-Paper deleted along with its PDF and page images.')
    return redirect('epaper:dashboard')
