from django.core.management.base import BaseCommand

from subscriptions.models import PlatformPolicy


POLICIES = {
    PlatformPolicy.PolicyType.CONTACT: {
        'title': 'Contact Us',
        'content': """
<h2>Business Contact</h2>
<p>Press Nexa is operated by <strong>SHRI INFOWAVE PRIVATE LIMITED</strong>.</p>
<ul>
  <li><strong>Registered office:</strong> 101 Govind Kund Tila, Radha Niwas, Vrindaban, Mathura, Mathura - 281121, Uttar Pradesh, India</li>
  <li><strong>Support email:</strong> srbc500@gmail.com</li>
  <li><strong>Business hours:</strong> Monday to Saturday, 10:00 AM to 6:00 PM IST</li>
  <li><strong>Website:</strong> https://pressnexa.live-app.in/</li>
</ul>
<h2>Support Scope</h2>
<p>Customers can contact us for account access, subscription, billing, onboarding, tenant setup, domain status, content management, ePaper, video, and platform support requests.</p>
<h2>Company Details</h2>
<p><strong>CIN:</strong> U62012UW2026PTC257361<br><strong>PAN:</strong> ABUCS7544P<br><strong>Date of incorporation:</strong> 17 August 2026</p>
""",
    },
    PlatformPolicy.PolicyType.PRIVACY: {
        'title': 'Privacy Policy',
        'content': """
<h2>Overview</h2>
<p>This Privacy Policy explains how Press Nexa, operated by SHRI INFOWAVE PRIVATE LIMITED, collects and uses information when customers use our SaaS platform.</p>
<h2>Information We Collect</h2>
<ul>
  <li>Account details such as name, username, email address, mobile number, and login information.</li>
  <li>Tenant and publication details such as business name, publication name, logo, branding, domain, content settings, onboarding details, and reviewer comments.</li>
  <li>Billing records such as selected plan, amount, currency, payment status, Razorpay order ID, payment ID, and transaction references.</li>
  <li>Usage and security data such as IP address, browser details, request logs, feature access, and support interactions.</li>
</ul>
<h2>Payment Information</h2>
<p>Payments are processed through Razorpay. Press Nexa does not store card numbers, UPI PINs, CVV, or sensitive payment credentials. Razorpay may collect and process payment information according to its own policies.</p>
<h2>How We Use Information</h2>
<ul>
  <li>To create and manage customer accounts, tenant workspaces, subscriptions, onboarding, and publication workflows.</li>
  <li>To provide support, verify payments, prevent misuse, improve services, and comply with legal or regulatory obligations.</li>
  <li>To enforce plan entitlements and show only features available for the selected subscription.</li>
</ul>
<h2>Sharing</h2>
<p>We share information only with service providers required to operate the platform, payment processors, hosting providers, support tools, legal authorities where required, or with the customer's authorization.</p>
<h2>Security and Retention</h2>
<p>We use reasonable technical and administrative safeguards to protect data. Records are retained as long as required for service delivery, legal compliance, accounting, dispute resolution, and security.</p>
<h2>Customer Requests</h2>
<p>For privacy requests, corrections, or account questions, contact srbc500@gmail.com.</p>
""",
    },
    PlatformPolicy.PolicyType.TERMS: {
        'title': 'Terms and Conditions',
        'content': """
<h2>Agreement</h2>
<p>By creating an account, purchasing a plan, or using Press Nexa, you agree to these Terms and Conditions. Press Nexa is operated by SHRI INFOWAVE PRIVATE LIMITED.</p>
<h2>Services</h2>
<p>Press Nexa provides a news publishing SaaS platform including tenant-aware CMS features, website pages, media management, themes, analytics, billing workflows, video, ePaper, domain setup support, and plan-based feature entitlements.</p>
<h2>Customer Responsibilities</h2>
<ul>
  <li>You are responsible for the legality, accuracy, ownership, and permissions of content uploaded or published through your tenant workspace.</li>
  <li>You must keep account credentials secure and ensure that your users follow applicable laws and platform policies.</li>
  <li>You must not use the platform for unlawful, misleading, infringing, abusive, or harmful activity.</li>
</ul>
<h2>Plans and Access</h2>
<p>Features are controlled by the active plan, billing cycle, add-ons, and tenant-specific entitlements. Press Nexa may restrict unavailable features and may suspend or limit accounts with failed, expired, past-due, or disputed payments.</p>
<h2>Domain, Review, and Publication</h2>
<p>Payment creates or activates a customer workflow, but publication, domain readiness, review, and final setup may require onboarding details and approval checks. Customers must provide accurate publication details.</p>
<h2>Intellectual Property</h2>
<p>Customers retain ownership of their uploaded content. Press Nexa retains rights in its platform software, workflows, design, code, templates, and technology.</p>
<h2>Limitation</h2>
<p>The service is provided on a commercially reasonable basis. We are not responsible for third-party downtime, payment processor issues, domain/DNS delays, search engine approvals, AdSense decisions, or customer content claims.</p>
<h2>Governing Law</h2>
<p>These terms are governed by the laws of India, subject to competent jurisdiction connected with the company's registered office in Uttar Pradesh.</p>
""",
    },
    PlatformPolicy.PolicyType.REFUND: {
        'title': 'Refund and Cancellation Policy',
        'content': """
<h2>Digital SaaS Service</h2>
<p>Press Nexa is a digital SaaS platform. Subscription payment is used to reserve, create, activate, and operate a tenant workspace and related services.</p>
<h2>Refund Eligibility</h2>
<p>Refunds may be considered only for duplicate payments, failed payments where money was deducted but not received by us, payment verification errors, or cases where the subscribed workspace could not be activated due to an issue from our side.</p>
<h2>Non-Refundable Cases</h2>
<p>After onboarding, tenant setup, custom configuration, domain assistance, publication setup, or active service usage has started, payments are generally non-refundable unless required by law or approved by the company.</p>
<h2>Cancellation</h2>
<p>Customers can request cancellation by contacting support. Cancellation stops future service access according to the current billing period and plan rules. Data retention and export support may be handled according to platform policy and technical feasibility.</p>
<h2>Refund Process</h2>
<p>To request a refund, email srbc500@gmail.com with your account email, payment ID, order ID, amount, and reason. Approved refunds are processed through Razorpay or the original payment method. Bank and payment gateway timelines may vary.</p>
""",
    },
    PlatformPolicy.PolicyType.BILLING: {
        'title': 'Subscription and Billing Policy',
        'content': """
<h2>Plan Management</h2>
<p>Press Nexa plans, prices, billing cycles, and feature entitlements are managed inside the Press Nexa admin system. Customers select an available plan from the website and pay through Razorpay checkout.</p>
<h2>Payment Flow</h2>
<p>For each purchase, Press Nexa creates a Razorpay order, verifies the payment signature after payment, records billing details, and activates the tenant subscription internally. Card, UPI, and bank-sensitive data are handled by Razorpay.</p>
<h2>Billing Cycles</h2>
<p>Plans may be monthly or yearly depending on the active plan price configured by the admin. Service access runs for the purchased billing period after successful payment verification.</p>
<h2>Renewals and Expiry</h2>
<p>Unless automatic recurring payment is separately enabled, customers must renew before the current period ends. Expired, failed, disputed, past-due, or suspended subscriptions may have restricted access until billing is resolved.</p>
<h2>Plan Changes</h2>
<p>Plan upgrades, downgrades, feature changes, and add-ons are controlled by platform rules and admin configuration. Effective entitlements are enforced in the dashboard, views, forms, and backend actions.</p>
<h2>Receipts and Records</h2>
<p>Billing records store the selected plan, billing cycle, amount, currency, Razorpay order/payment references, and payment status for audit and support.</p>
""",
    },
    PlatformPolicy.PolicyType.GRIEVANCE: {
        'title': 'Support and Grievance Information',
        'content': """
<h2>Support Contact</h2>
<p>For account, billing, payment, onboarding, tenant setup, or platform issues, contact Press Nexa support at srbc500@gmail.com.</p>
<h2>Grievance Details</h2>
<p>Press Nexa is operated by SHRI INFOWAVE PRIVATE LIMITED, CIN U62012UW2026PTC257361, with registered office at 101 Govind Kund Tila, Radha Niwas, Vrindaban, Mathura, Mathura - 281121, Uttar Pradesh, India.</p>
<h2>Required Information</h2>
<p>Please include your registered email address, tenant/publication name, payment ID or order ID if relevant, screenshots, and a clear description of the issue.</p>
<h2>Response Timeline</h2>
<p>We aim to acknowledge support and grievance emails within 2 business days and work toward resolution within 7 business days where the issue is within our control. Complex third-party, banking, domain, DNS, or payment gateway issues may take longer.</p>
""",
    },
}


class Command(BaseCommand):
    help = 'Create or update public platform policies for Press Nexa.'

    def handle(self, *args, **options):
        for policy_type, data in POLICIES.items():
            policy, created = PlatformPolicy.objects.update_or_create(
                policy_type=policy_type,
                defaults={
                    'title': data['title'],
                    'content': data['content'].strip(),
                    'is_published': True,
                },
            )
            action = 'Created' if created else 'Updated'
            self.stdout.write(self.style.SUCCESS(f'{action}: {policy.title}'))
