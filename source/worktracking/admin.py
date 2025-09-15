import datetime
from django.contrib import admin
from django.db.models import Max
from django.urls import path
from django.shortcuts import render
from django.http import HttpRequest
from django.utils.html import format_html
from django.urls import reverse
from django import forms
from django.db.models import Count, Q
from worktracking.models import Line, Outing, TeamMember, Issue, CompletionStatus, CompletionReport

admin.site.site_header = "Transect Admin"  # Main header text
admin.site.site_title = "Transect Admin"    # Browser tab title
admin.site.index_title = "Transect Admin"  # Dashboard subtitle

# Create custom forms with sized inputs
class LineForm(forms.ModelForm):
    class Meta:
        model = Line
        fields = '__all__'
        widgets = {
            'start_station_id': forms.TextInput(attrs={'size': 5}),
            'end_station_id': forms.TextInput(attrs={'size': 5}),
        }

class OutingForm(forms.ModelForm):
    class Meta:
        model = Outing
        fields = '__all__'
        widgets = {
            'start_station_id': forms.TextInput(attrs={'size': 5}),
            'end_station_id': forms.TextInput(attrs={'size': 5}),
        }

class IssueForm(forms.ModelForm):
    class Meta:
        model = Issue
        fields = '__all__'
        widgets = {
            'start_station_id': forms.TextInput(attrs={'size': 5}),
            'end_station_id': forms.TextInput(attrs={'size': 5}),
        }

class OutingInline(admin.TabularInline):
    model = Outing
    form = OutingForm
    extra = 0
    can_add = False
    can_delete = False
    show_change_link = True
    fields = ('date', 'completion_status', 'hours', 'number_of_workers')
    readonly_fields = fields
    verbose_name = "Outing"
    verbose_name_plural = "Outings"

class IssueInline(admin.TabularInline):
    model = Issue
    form = IssueForm
    extra = 0
    fields = ('issue_status', 'start_station_id', 'issue_type', 'station_type', 'end_station_id', 'description', 'photo')
    verbose_name = "Issue"
    verbose_name_plural = "Issues"

@admin.register(Line)
class LineAdmin(admin.ModelAdmin):
    form = LineForm
    inlines = [OutingInline, IssueInline]
    list_display = ('name', 'line_type', 'start_station_id', 'end_station_id',
                    'outing_count', 'completed_outings_count', 'issue_count',)
    list_filter = ('line_type',)
    search_fields = ('name', 'start_station_id', 'end_station_id')
    inlines = [OutingInline, IssueInline]
    readonly_fields = ('outings_list', 'issues_list')
    fieldsets = (
        (None, {
            'fields': ('name', 'line_type', 'start_station_id', 'end_station_id')
        }),
    )

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('completion-report/', self.admin_site.admin_view(self.completion_report),
                 name='worktracking_line_completion_report'),
        ]
        return custom_urls + urls

    def outings_list(self, obj):
        outings = obj.outings.all()
        if outings:
            links = []
            for outing in outings:
                url = reverse('admin:worktracking_outing_change', args=[outing.id])
                links.append(f'<a href="{url}">{outing.date} - {outing.get_completion_status_display()}</a>')
            return format_html('<br>'.join(links))
        return "No outings yet"
    outings_list.short_description = 'Outings'

    def issues_list(self, obj):
        issues = obj.issues.all()
        if issues:
            links = []
            for issue in issues:
                url = reverse('admin:worktracking_issue_change', args=[issue.id])
                links.append(f'<a href="{url}">{issue.start_station_id}: {issue.get_issue_type_display()}</a>')
            return format_html('<br>'.join(links))
        return "No issues yet"
    issues_list.short_description = 'Issues'

        # Add custom methods for counts
    def issue_count(self, obj):
        return obj.issues.count()
    issue_count.short_description = 'Issues'
    issue_count.admin_order_field = 'issue_count'

    def outing_count(self, obj):
        return obj.outings.count()
    outing_count.short_description = 'Outings'
    outing_count.admin_order_field = 'outing_count'

    def completed_outings_count(self, obj):
        return obj.outings.filter(completion_status=CompletionStatus.COMPLETED).count()
    completed_outings_count.short_description = 'Completed'
    completed_outings_count.admin_order_field = 'completed_outing_count'

    # Optimize queryset to reduce database queries
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(
            issue_count=Count('issues'),
            outing_count=Count('outings'),
            completed_outing_count=Count('outings', filter=Q(outings__completion_status=CompletionStatus.COMPLETED))
        )
        return queryset

    def completion_report(self, request: HttpRequest):
        # Get sort parameter from request
        sort_by = request.GET.get('sort', 'last_completed')
        sort_order = request.GET.get('order', 'desc')

        # Get all lines with their completion statistics
        lines = Line.objects.all()

        report_data = []
        for line in lines:
            # Get completed outings
            completed_outings = line.outings.filter(completion_status=CompletionStatus.COMPLETED)
            last_completed = completed_outings.aggregate(Max('date'))['date__max']
            completed_count = completed_outings.count()

            # Get partial outings
            partial_outings = line.outings.filter(completion_status=CompletionStatus.PARTIAL)
            last_partial = partial_outings.aggregate(Max('date'))['date__max']
            partial_count = partial_outings.count()

            # Generate admin URL for this line
            line_admin_url = reverse('admin:worktracking_line_change', args=[line.id])

            report_data.append({
                'line': line,
                'line_admin_url': line_admin_url,  # Add the admin URL
                'last_completed': last_completed,
                'completed_count': completed_count,
                'last_partial': last_partial,
                'partial_count': partial_count,
            })

        # Define sorting functions
        def sort_key_last_completed(x):
            return x['last_completed'] or datetime.date.min

        def sort_key_last_partial(x):
            return x['last_partial'] or datetime.date.min

        def sort_key_completed_count(x):
            return x['completed_count']

        def sort_key_partial_count(x):
            return x['partial_count']

        def sort_key_line_name(x):
            return x['line'].name

        # Apply sorting based on parameters
        sort_functions = {
            'last_completed': sort_key_last_completed,
            'last_partial': sort_key_last_partial,
            'completed_count': sort_key_completed_count,
            'partial_count': sort_key_partial_count,
            'line_name': sort_key_line_name,
        }

        if sort_by in sort_functions:
            report_data.sort(key=sort_functions[sort_by], reverse=(sort_order == 'desc'))

        context = {
            **self.admin_site.each_context(request),
            'title': 'Line Completion Report',
            'report_data': report_data,
            'opts': self.model._meta,
            'sort_by': sort_by,
            'sort_order': sort_order,
        }

        return render(request, 'admin/worktracking/line/completion_report.html', context)

@admin.register(CompletionReport)
class CompletionReportAdmin(admin.ModelAdmin):
    # This makes the proxy model appear in the admin but only for viewing the report
    def changelist_view(self, request, extra_context=None):
        # Redirect to the completion report
        from django.shortcuts import redirect
        return redirect('admin:worktracking_line_completion_report')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        # Only show to users with permission to view lines
        return request.user.has_perm('worktracking.view_line')

@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = ('name', 'email_address')
    search_fields = ('name', 'email_address')


@admin.register(Outing)
class OutingAdmin(admin.ModelAdmin):
    form = OutingForm
    list_display = ('date', 'route', 'completion_status', 'start_station_id', 'end_station_id', 'hours', 'number_of_workers', 'get_participants')
    list_filter = ('date', 'route', 'completion_status')
    fieldsets = (
        (None, {
            'fields': ('date', 'route', 'completion_status', 'hours', 'number_of_workers', 'start_station_id', 'end_station_id')
        }),
        ('Participants', {
            'classes': ('collapse',),  # This fieldset will be collapsed by default
            'fields': ('participants',),
        }),
    )
    filter_horizontal = ('participants',)
    inlines = [IssueInline]

    def get_participants(self, obj):
        return ", ".join([p.name for p in obj.participants.all()])
    get_participants.short_description = 'Team Members'

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('participants')

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, Issue) and not instance.line_id:
                instance.line = form.instance.route
            instance.save()
        formset.save_m2m()

@admin.register(Issue)
class IssueAdmin(admin.ModelAdmin):
    form = IssueForm
    list_display = ('line', 'issue_status', 'start_station_id', 'outing', 'issue_type', 'description')
    list_filter = ('issue_status', 'issue_type', 'station_type')
    search_fields = ('start_station_id', 'description')
