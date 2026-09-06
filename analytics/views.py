from datetime import timedelta
from django import forms
from django.contrib import messages
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST
from .forms import PlatformEnquiryForm
from .models import PlatformEnquiry, PlatformVisit
from .tracking import tracking_allowed, visitor_for_request
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from core.models import user_can_access_tenant
from tenants.views import is_platform_admin

from .services import platform_metrics, tenant_analytics


@login_required
@user_passes_test(is_platform_admin)
def super_admin_dashboard(request):
    return render(request, 'analytics/super_admin_dashboard.html', {'metrics': platform_metrics()})


@login_required
def tenant_analytics_dashboard(request):
    if not user_can_access_tenant(request.user, request.tenant):
        raise PermissionDenied("You do not have access to this tenant.")
    return render(request, 'analytics/tenant_dashboard.html', {'analytics': tenant_analytics(request.tenant)})

@require_http_methods(['GET', 'POST'])
@never_cache
def platform_contact(request):
    if getattr(request, 'tenant', None):
        from subscriptions.views import policy_page
        return policy_page(request, 'contact')
    from subscriptions.models import PlatformPolicy
    from subscriptions.support import company_profile
    form = PlatformEnquiryForm(request.POST if request.method == 'POST' else None)
    status = 200
    if request.method == 'POST':
        # Use only the directly connected address; never trust arbitrary forwarded headers.
        key = 'platform-enquiry:' + salted_hmac('enquiry-rate', request.META.get('REMOTE_ADDR', '')).hexdigest()
        cache.add(key, 0, timeout=60)
        try:
            attempts = cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=60)
            attempts = 1
        if attempts > 5:
            form.is_valid()
            form.add_error(None, 'Too many attempts. Please wait a minute and try again.')
            status = 429
        elif form.is_valid():
            with transaction.atomic():
                enquiry = form.save(commit=False)
                enquiry.consent_at = timezone.now()
                if tracking_allowed(request):
                    enquiry.visitor = visitor_for_request(request)
                if request.user.is_authenticated:
                    enquiry.user = request.user
                enquiry.save()
            request._platform_enquiry_saved = enquiry.visitor_id is not None
            messages.success(request, 'Thank you. Your enquiry has been saved; our team will follow up using your contact details.')
            return redirect('contact_us')
        else:
            status = 400
    policy = PlatformPolicy.objects.filter(policy_type='contact', is_published=True).first()
    return render(request, 'analytics/contact.html', {
        'form': form, 'company': company_profile(), 'policy': policy,
    }, status=status)


class VisitorReportFilter(forms.Form):
    start = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    end = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    visitor = forms.UUIDField(required=False, widget=forms.HiddenInput)

    def clean(self):
        data = super().clean()
        if data.get('start') and data.get('end') and data['start'] > data['end']:
            raise forms.ValidationError('Start date must be before the end date.')
        return data


def require_platform_access(request):
    if getattr(request, 'tenant', None) or not is_platform_admin(request.user):
        raise PermissionDenied('Platform administrator access required.')


@login_required
@never_cache
def visitor_report(request):
    require_platform_access(request)
    today = timezone.localdate()
    data = request.GET.copy()
    data.setdefault('start', (today - timedelta(days=29)).isoformat())
    data.setdefault('end', today.isoformat())
    form = VisitorReportFilter(data)
    visits = PlatformVisit.objects.none()
    enquiries = PlatformEnquiry.objects.none()
    selected_visitor = None
    if form.is_valid():
        visits = PlatformVisit.objects.filter(occurred_at__date__range=(form.cleaned_data['start'], form.cleaned_data['end']))
        enquiries = PlatformEnquiry.objects.filter(created_at__date__range=(form.cleaned_data['start'], form.cleaned_data['end']))
        selected_visitor = form.cleaned_data.get('visitor')
        if selected_visitor:
            visits = visits.filter(visitor_id=selected_visitor)
            enquiries = enquiries.filter(visitor_id=selected_visitor)
    pages = visits.filter(kind='page')
    metrics = {
        'page_views': pages.count(),
        'visitors': visits.values('visitor_id').distinct().count(),
        'sessions': visits.values('session_id').distinct().count(),
        'returning_sessions': visits.filter(is_returning=True).values('session_id').distinct().count(),
        'signups': visits.filter(kind='signup').count(),
        'enquiries': enquiries.count(),
    }
    return render(request, 'analytics/visitors.html', {
        'filter_form': form, 'metrics': metrics, 'selected_visitor': selected_visitor,
        'visits': Paginator(visits.select_related('visitor', 'user'), 30).get_page(request.GET.get('page')),
        'enquiries': Paginator(enquiries.select_related('user'), 20).get_page(request.GET.get('enquiry_page')),
        'top_pages': pages.order_by().values('path').annotate(total=Count('id')).order_by('-total', 'path')[:10],
        'sources': pages.order_by().values('referrer_domain').annotate(total=Count('id')).order_by('-total', 'referrer_domain')[:10],
        'daily': list(pages.order_by().annotate(day=TruncDate('occurred_at')).values('day').annotate(total=Count('id'), visitors=Count('visitor_id', distinct=True)).order_by('-day')[:31]),
        'statuses': PlatformEnquiry.Status.choices,
    })


@login_required
@require_POST
def update_enquiry(request, pk):
    require_platform_access(request)
    enquiry = get_object_or_404(PlatformEnquiry, pk=pk)
    status = request.POST.get('status')
    if status not in PlatformEnquiry.Status.values:
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest('Invalid enquiry status.')
    enquiry.status = status
    enquiry.notes = request.POST.get('notes', '')[:5000]
    enquiry.save(update_fields=['status', 'notes'])
    messages.success(request, 'Enquiry updated.')
    return redirect('analytics:visitor_report')
