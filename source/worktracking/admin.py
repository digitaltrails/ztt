import datetime
import csv
from django.contrib import admin
from django.db.models import Max
from django.urls import path
from django.shortcuts import render
from django.http import HttpRequest, HttpResponse
from django.utils.html import format_html
from django.urls import reverse
from django import forms
from django.db.models import Count, Q
from import_export import resources
from import_export.admin import ImportExportModelAdmin, ExportActionMixin
from worktracking.models import Line, Outing, TeamMember, Issue, CompletionStatus, CompletionReport, Audit, IssueStatusEnum

from worktracking.resources import LineCompletionResource

admin.site.site_header = "Transect Admin"  # Main header text
admin.site.site_title = "Transect Admin"    # Browser tab title
admin.site.index_title = "Transect Admin"  # Dashboard subtitle
from django.forms import CheckboxSelectMultiple


class HorizontalCheckboxSelectMultiple(CheckboxSelectMultiple):
    template_name = 'forms/widgets/horizontal_checkbox_select.html'

    def __init__(self, columns=3, *args, **kwargs):
        self.columns = columns
        super().__init__(*args, **kwargs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context['widget']['columns'] = self.columns
        return context

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
            'participants': HorizontalCheckboxSelectMultiple(columns=4),
        }

class IssueForm(forms.ModelForm):
    class Meta:
        model = Issue
        fields = '__all__'
        widgets = {
            'start_station_id': forms.TextInput(attrs={'size': 5}),
            'end_station_id': forms.TextInput(attrs={'size': 5}),
            'description': forms.Textarea(attrs={'rows': 3, 'cols': 55}),
        }

class OutingInline(admin.TabularInline):
    model = Outing
    ordering = ('-date',)
    form = OutingForm
    extra = 0
    can_add = False
    can_delete = False
    show_change_link = True
    fields = ('date', 'completion_status', 'start_station_id', 'end_station_id', 'hours', 'number_of_workers')
    readonly_fields = fields
    verbose_name = "Outing"
    verbose_name_plural = "Outings"

class IssueInline(admin.TabularInline):
    model = Issue
    ordering = ('-issue_status',)
    form = IssueForm
    extra = 0
    show_change_link = True
    fields = ('issue_status', 'start_station_id', 'end_station_id', 'issue_type', 'station_type', 'description', 'photo')
    verbose_name = "Issue"
    verbose_name_plural = "Issues"

@admin.register(Line)
class LineAdmin(ImportExportModelAdmin):
    def has_import_permission(self, request):
        return request.user.is_superuser

    form = LineForm
    inlines = [OutingInline, IssueInline]
    list_display = ('name', 'line_type', 'start_station_id', 'end_station_id',
                    'outing_count', 'completed_outings_count', 'unresolved_issue_count',)
    list_filter = ('line_type',)
    search_fields = ('name', 'start_station_id', 'end_station_id')
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

    # Updated methods to use annotated values
    def issue_count(self, obj):
        # Use the annotated value if available
        if hasattr(obj, 'issue_count'):
            return obj.issue_count
        return obj.issues.count()
    issue_count.short_description = 'Issues'
    issue_count.admin_order_field = 'issue_count'

    def unresolved_issue_count(self, obj):
        # Use the annotated value if available
        if hasattr(obj, 'unresolved_issue_count'):
            return obj.unresolved_issue_count
        return obj.issues.exclude(issue_status=IssueStatusEnum.FIXED).exclude(issue_status=IssueStatusEnum.NO_ACTION_REQ).count()
    unresolved_issue_count.short_description = 'Unresolved issues'
    unresolved_issue_count.admin_order_field = 'unresolved_issue_count'

    def outing_count(self, obj):
        # Use the annotated value if available
        if hasattr(obj, 'outing_count'):
            return obj.outing_count
        return obj.outings.count()
    outing_count.short_description = 'Outings'
    outing_count.admin_order_field = 'outing_count'

    def completed_outings_count(self, obj):
        # Use the annotated value if available
        if hasattr(obj, 'completed_outing_count'):
            return obj.completed_outing_count
        return obj.outings.filter(completion_status=CompletionStatus.COMPLETED).count()
    completed_outings_count.short_description = 'Completed'
    completed_outings_count.admin_order_field = 'completed_outing_count'

    # Optimize queryset to reduce database queries
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = queryset.annotate(
            issue_count=Count('issues', distinct=True),
            outing_count=Count('outings', distinct=True),
            completed_outing_count=Count('outings', filter=Q(outings__completion_status=CompletionStatus.COMPLETED),
                                         distinct=True)
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

            # get issues that need work
            issues_count = line.issues.count()
            issues_unresolved_count = line.issues.exclude(issue_status=IssueStatusEnum.FIXED).exclude(issue_status=IssueStatusEnum.NO_ACTION_REQ).count()

            # Generate admin URL for this line
            line_admin_url = reverse('admin:worktracking_line_change', args=[line.id])

            resource = LineCompletionResource()
            resource.line = line
            resource.line_name = line.name
            resource.line_admin_url = line_admin_url
            resource.line_type = line.line_type
            resource.last_partial = last_partial
            resource.last_completed = last_completed
            resource.completed_count = completed_count
            resource.partial_count = partial_count
            resource.issues_unresolved_count = issues_unresolved_count
            resource.issues_count = issues_count
            report_data.append(resource)

        if request.GET.get('format') == 'csv':
            dataset = LineCompletionResource().export(report_data)
            response = HttpResponse(dataset.csv, content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="line_completion_report.csv"'
            return response

        # Define sorting functions
        def sort_key_last_completed(x):
            return x.last_completed or datetime.date.min

        def sort_key_last_partial(x):
            return x.last_partial or datetime.date.min

        def sort_key_completed_count(x):
            return x.completed_count

        def sort_key_partial_count(x):
            return x.partial_count

        def sort_key_issues_count(x):
            return x.issues_count

        def sort_key_issues_unresolved_count(x):
            return x.issues_unresolved_count

        def sort_key_line_name(x):
            return x.line_name

        # Apply sorting based on parameters
        sort_functions = {
            'last_completed': sort_key_last_completed,
            'last_partial': sort_key_last_partial,
            'completed_count': sort_key_completed_count,
            'partial_count': sort_key_partial_count,
            'line_name': sort_key_line_name,
            'issues_unresolved_count': sort_key_issues_unresolved_count,
            'issues_count': sort_key_issues_count,
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
class TeamMemberAdmin(ImportExportModelAdmin):

    def has_import_permission(self, request):
        return request.user.is_superuser

    list_display = ('name', 'available')
    list_filter = ('available',)
    search_fields = ('name', 'available')

@admin.register(Outing)
class OutingAdmin(ImportExportModelAdmin):

    def has_import_permission(self, request):
        return request.user.is_superuser

    form = OutingForm
    list_display = ('date', 'route', 'completion_status', 'start_station_id', 'end_station_id', 'hours', 'number_of_workers',
                    'get_participants', 'normalized_minutes_per_station')
    list_filter = ('completion_status', 'date', 'participants', 'route',)
    fieldsets = (
        (None, {
            'fields': ('date', 'route', 'completion_status', 'hours', 'number_of_workers', 'start_station_id', 'end_station_id', 'participants')
        }),
    )
    filter_horizontal = ('participants',)
    inlines = [IssueInline]

    def get_participants(self, obj):
        return ", ".join([p.name for p in obj.participants.all()])
    get_participants.short_description = 'Team Members'

    def normalized_minutes_per_station(self, obj):
        # Handle cases where hours is 0 or None
        try:
            if not obj.hours or obj.hours == 0 or obj.number_of_workers == 0:
                return "N/A"
            num_stns = abs(int(obj.start_station_id) - int(obj.end_station_id))
            minutes_per = (obj.hours * 60 / num_stns)
            normalized_minutes_per = (obj.hours * 60 / num_stns) * (obj.number_of_workers / 3)
            return f"{minutes_per:.2f}  [{normalized_minutes_per:.2f}]"  # Round to 2 decimal places
        except (TypeError, ValueError):
             return "N/A"

    # Set column header name
    normalized_minutes_per_station.short_description = 'Mins/Stn [Normalized]'

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('participants')

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, Issue) and not instance.line_id:
                instance.line = form.instance.route
            instance.save()
        formset.save_m2m()

class IssueResource(resources.ModelResource):
    class Meta:
        model = Issue
        fields = ('id', 'line', 'issue_status', 'start_station_id', 'end_station_id',
                  'station_type', 'outing', 'issue_type', 'outing', 'origin', 'last_action_date', 'description')

@admin.register(Issue)
class IssueAdmin(ImportExportModelAdmin):

    def has_import_permission(self, request):
        return request.user.is_superuser

    form = IssueForm
    resource_class = IssueResource
    list_display = ('line', 'issue_status', 'start_station_id', 'outing', 'issue_type', 'last_action_date', 'description')
    list_filter = ('issue_status', 'issue_type', 'station_type', 'origin', 'reported_by')
    search_fields = ('start_station_id', 'description', 'origin', 'reported_by')

@admin.register(Audit)
class AuditAdmin(ExportActionMixin, admin.ModelAdmin):
    list_display = ('when', 'action', 'username', 'ip',)
    list_filter = ('action', )
    readonly_fields = ('when',)

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
