# resources.py
from import_export import resources, fields
from worktracking.models import Line  # Your line model


class LineCompletionResource(resources.Resource):
    line_name = fields.Field(attribute='line__name', column_name='Line Name')
    line_type = fields.Field(attribute='line__get_line_type_display', column_name='Type')
    last_completed = fields.Field(column_name='Last Completed')
    last_partial = fields.Field(column_name='Last Partial')
    completed_count = fields.Field(column_name='Completed Count')
    partial_count = fields.Field(column_name='Partial Count')
    issues_unresolved_count = fields.Field(column_name='Unresolved Issues')
    issues_count = fields.Field(column_name='Total Issues')

    def dehydrate_last_completed(self, item):
        return item.last_completed or 'Never'

    def dehydrate_last_partial(self, item):
        return item.last_partial or 'Never'

    def dehydrate_completed_count(self, item):
        return item.completed_count or 0

    def dehydrate_partial_count(self, item):
        return item.partial_count or 0

    def dehydrate_issues_unresolved_count(self, item):
        return item.issues_unresolved_count or 0

    def dehydrate_issues_count(self, item):
        return item.issues_count or 0