import datetime
from django.contrib import admin
from django.contrib.admin.views.main import ChangeList
from django.db.models import Max, IntegerField, Case, When, Value
from django.db.models.functions import Cast
from django.urls import path
from django.shortcuts import render
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
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


class DynPaginationChangeList(ChangeList):

    normal = 100
    unlimited = 10_000

    def __init__(self, request, model, list_display, list_display_links, list_filter, date_hierarchy, search_fields, list_select_related, list_per_page, list_max_show_all, list_editable, model_admin, sortable_by, search_help_text):
        page_param = request.GET.get('list_per_page', None)
        if page_param is not None:
            # Override list_per_page if present in URL
            # Need to be before super call to be applied on filters
            list_per_page = int(page_param)
            if list_per_page == 0:
                list_per_page = DynPaginationChangeList.unlimited
        self.unlimited = list_per_page == DynPaginationChangeList.unlimited
        super(DynPaginationChangeList, self).__init__(request, model, list_display, list_display_links, list_filter, date_hierarchy, search_fields, list_select_related, list_per_page, list_max_show_all, list_editable, model_admin, sortable_by, search_help_text)

    def get_filters_params(self, params=None):
        """
        Return all params except IGNORED_PARAMS and 'list_per_page'
        """
        lookup_params = super(DynPaginationChangeList, self).get_filters_params(params)
        if 'list_per_page' in lookup_params:
            del lookup_params['list_per_page']
        return lookup_params

    def is_unlimted(self):
        return self.list_per_page == DynPaginationChangeList.unlimited

class AdminDynPaginationMixin:
    def get_changelist(self, request, **kwargs):
        return DynPaginationChangeList

class TransectModelAdmin(AdminDynPaginationMixin, admin.ModelAdmin):
    def changelist_view(self, request, extra_context=None):
        # Change default number of per page
        page_param = int(request.GET.get('list_per_page', [DynPaginationChangeList.normal])[0])
        if page_param == 0:
            page_param = DynPaginationChangeList.unlimited
        # Dynamically set the django admin list size based on query parameter.
        self.list_per_page = page_param
        return super(TransectModelAdmin, self).changelist_view(request, extra_context)

    def _make_related_link(self, obj, field_name, app_label, model_name, allow_breaks=False):
        related_obj = getattr(obj, field_name, None)
        if related_obj:
            url = reverse(f'admin:{app_label}_{model_name}_change', args=[related_obj.id])
            if allow_breaks:
                html = '<span><a target="_blank" rel="noopener" href="{}">{}</a></span>'
            else:
                html =  '<span style="white-space: nowrap;"><a target="_blank" rel="noopener" href="{}">{}</a></span>'

            return format_html(html, url, related_obj)
        return "-"

class CompactModelForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field_name, field in self.fields.items():
            # Get the model field
            model_field = self._meta.model._meta.get_field(field_name)

            # If it's a CharField with max_length, set HTML attributes
            if hasattr(model_field, 'max_length') and model_field.max_length:
                if isinstance(field.widget, forms.TextInput):
                    field.widget.attrs.update({
                        'maxlength': model_field.max_length,
                        'size': min(model_field.max_length, 50),  # Cap at 50 for very long fields
                        'style': f'width: {min(model_field.max_length, 50)}ch;'
                    })

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
class LineForm(CompactModelForm):
    class Meta:
        model = Line
        fields = '__all__'
        widgets = {
            'start_station_id': forms.TextInput(attrs={'size': 5}),
            'end_station_id': forms.TextInput(attrs={'size': 5}),
        }

class OutingForm(CompactModelForm):
    class Meta:
        model = Outing
        fields = '__all__'
        widgets = {
            'start_station_id': forms.TextInput(attrs={'size': 5}),
            'end_station_id': forms.TextInput(attrs={'size': 5}),
            'participants': HorizontalCheckboxSelectMultiple(columns=4),
        }

class IssueForm(CompactModelForm):
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
    fields = ('date', 'completion_status', 'start_station_id', 'end_station_id', 'hours', 'number_of_workers', 'participants',
              'minutes_per_station', 'normalized_minutes_per_station', )
    readonly_fields = fields
    verbose_name = "Outing"
    verbose_name_plural = "Outings"

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        # Allow viewing but not changing
        return bool(obj) and request.method == 'GET'

class IssueInline(admin.TabularInline):
    model = Issue

    def get_queryset(self, request):  # Order text field numerically
        # Get the base queryset
        qs = super().get_queryset(request)
        qs = qs.annotate(
            numeric_field=Cast('start_station_id', IntegerField())
        ).order_by('numeric_field')
        return qs

    form = IssueForm
    extra = 1
    show_change_link = True
    fields = ('issue_status', 'start_station_id', 'end_station_id', 'issue_type', 'station_type', 'description', 'photo')
    readonly_fields = ()
    verbose_name = "Issue"
    verbose_name_plural = "Issues"

@admin.register(Line)
class LineAdmin(TransectModelAdmin):
    def has_import_permission(self, request):
        return request.user.is_superuser

    form = LineForm
    inlines = [OutingInline, IssueInline]
    list_display = ('name', 'line_type', 'start_station_id', 'end_station_id', 'work_priority_display',
                    'outing_count', 'completed_outings_count', 'unresolved_issue_count',)
    list_filter = ('line_type', 'work_priority',)
    search_fields = ('name', 'start_station_id', 'end_station_id', 'work_priority')
    readonly_fields = ('outings_list', 'issues_list')
    fieldsets = (
        (None, {
            'fields': ('name', 'line_type', 'start_station_id', 'end_station_id', 'work_priority')
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
                                         distinct=True),
            unresolved_issue_count=Count(
                'issues',
                filter=(~Q(issues__issue_status=IssueStatusEnum.NO_ACTION_REQ) &
                        ~Q(issues__issue_status=IssueStatusEnum.FIXED)),
                distinct=True),
            ordered_work_priority=Case(
                # Keep natural values for non-NULL, set NULL to 99
                When(work_priority__isnull=True, then=Value(99)),
                default='work_priority',  # Use the natural value for non-NULL
                output_field=IntegerField(),
            )
        )
        return queryset

    def work_priority_display(self, obj):
        if obj.work_priority is None:
            return "-"  # Or whatever display you want for NULL
        return obj.work_priority  # Display the natural value

    work_priority_display.admin_order_field = 'ordered_work_priority'
    work_priority_display.short_description = 'Priority'

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
            resource.work_priority = line.work_priority
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

        def sort_key_work_priority(x):
            return x.work_priority

        # Apply sorting based on parameters
        sort_functions = {
            'work_priority': sort_key_work_priority,
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
class TeamMemberAdmin(TransectModelAdmin):

    def has_import_permission(self, request):
        return request.user.is_superuser

    list_display = ('name', 'available')
    list_filter = ('available',)
    search_fields = ('name', 'available')

@admin.register(Outing)
class OutingAdmin(TransectModelAdmin):

    def has_import_permission(self, request):
        return request.user.is_superuser

    form = OutingForm
    list_display = ('date', 'route_link', 'completion_status', 'start_station_id', 'end_station_id', 'hours', 'number_of_workers',
                    'minutes_per_station', 'normalized_minutes_per_station', 'get_participants',)
    list_filter = ('completion_status', 'date', 'participants', 'route',)
    readonly_fields = ('minutes_per_station', 'normalized_minutes_per_station', )
    fieldsets = (
        (None, {
            'fields': ('date', 'route', 'completion_status', 'hours', 'number_of_workers', 'start_station_id', 'end_station_id',
                       'participants',('minutes_per_station', 'normalized_minutes_per_station',) )
        }),
    )
    filter_horizontal = ('participants',)
    inlines = [IssueInline]

    def route_link(self, obj):
        return self._make_related_link(obj, 'route', 'worktracking', 'line')

    route_link.short_description = 'Route'
    route_link.admin_order_field = 'route'

    def get_participants(self, obj):
        return ", ".join([p.name for p in obj.participants.all()])
    get_participants.short_description = 'Team Members'

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('participants')

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "participants":
            # Get the current outing instance if editing existing
            obj_id = request.resolver_match.kwargs.get('object_id')
            total_count = TeamMember.objects.count()
            if obj_id:
                # Editing existing outing - Show available members and current participants in this outing
                current_outing = Outing.objects.get(pk=obj_id)
                current_participants = current_outing.participants.all()
                available_members = TeamMember.objects.filter(available=True)
                kwargs["queryset"] = (available_members | current_participants).distinct()
                kwargs["help_text"] = "Showing existing participants and available team members (unavailable team members are not shown, unless already participating)."
            else:
                # Creating new outing - only show available
                available_count = TeamMember.objects.filter(available=True).count()
                kwargs["queryset"] = TeamMember.objects.filter(available=True)
                kwargs["help_text"] = (f"These {available_count} team members are available for outings "
                                       f"({total_count - available_count} unavailable team members are not shown).")
        return super().formfield_for_manytomany(db_field, request, **kwargs)

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
                  'station_type', 'outing', 'issue_type', 'outing', 'origin', 'created_at', 'description')

@admin.register(Issue)
class IssueAdmin(TransectModelAdmin):

    def has_import_permission(self, request):
        return request.user.is_superuser

    form = IssueForm
    resource_class = IssueResource
    list_display = ('id', 'line_link', 'issue_status', 'start_station_id', 'outing_link', 'issue_type', 'date_only', 'description')
    list_filter = ('issue_status', 'issue_type', 'station_type', 'origin', 'reported_by')
    search_fields = ('start_station_id', 'description', 'origin', 'reported_by')
    readonly_fields = ('created_at', 'updated_at')

    def date_only(self, obj):
        by = (' ' + obj.reported_by) if obj.reported_by else ''
        #origin = (' ' + obj.origin) if obj.origin else ''
        when = obj.created_at.strftime("%d/%m/%y") if obj.created_at else '-'
        return when + by #+ origin
    date_only.short_description = 'Created'

    def line_link(self, obj):
        return self._make_related_link(obj, 'line', 'worktracking', 'line')

    line_link.short_description = 'Line'
    line_link.admin_order_field = 'line'

    def outing_link(self, obj):
        return self._make_related_link(obj, 'outing', 'worktracking', 'outing', allow_breaks=True)

    outing_link.short_description = 'Outing'
    outing_link.admin_order_field = 'outing'

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
