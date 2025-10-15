from django.db import models
from django.core.validators import MinValueValidator
from django.db import models
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

class CompletionStatus(models.TextChoices):
    COMPLETED = 'Completed', 'Completed'
    PARTIAL = 'Partial', 'Partially Worked On'

class LineType(models.TextChoices):
    TRANSECT = 'Transect', 'Transect'
    MOUSELINE = 'MouseLine', 'Mouse-Line'

class StationType(models.TextChoices):
    NOVACOIL = 'Novacoil', 'Novacoil'
    NOVACOIL_BOXED = 'NovacoilBoxed', 'Novacoil-Boxed'
    WOODEN_BOX = 'WoodenBox', 'Wooden-Box'
    WEIRD_BOX = 'WeirdBox', 'Weird-Box'
    NA = 'NA', 'N/A'

class IssueEnum(models.TextChoices):
    COMPLICATED = 'Complicated', 'Complicated'
    MISSING_STATION = 'MissingStation', 'Missing Station'
    MISSING_HOOP = 'MissingHoop', 'Missing Hoop'
    MISSING_LID = 'MissingLid', 'Missing Lid'
    MISSING_MESH = 'MissingMesh', 'Missing Mesh'
    NEEDS_NEW_ICC = 'Needs_New_ICC', 'Needs new ICC'
    NEEDS_REPLACING = 'NeedsReplacing', 'Needs Replacing'
    SLIGHTLY_ROTTEN = 'SlightlyRotten', 'Slightly Rotten'
    VERY_ROTTEN = 'VeryRotten', 'Very Rotten'
    RUSTING_HOOP = 'RustingHoop', 'Rusting Hoop'
    NEEDS_CLEARING = 'NeedsClearing', 'Needs Clearing'
    NEEDS_ROPE = 'NeedsRope', 'Needs Rope'
    NEEDS_FREQUENT_ATTN = 'NeedsFrequentAttn', 'Needs Frequent Attention'
    ROPE_ON_DEAD_TREE = 'RopeOnDeadTree', 'Rope On Dead Tree'
    REQUIRES_CHAINSAW = 'RequiresChainsaw', 'Requires Chainsaw'
    SAFETY = 'Safety', 'Safety'
    FLORA = 'Flora', 'Flora'
    FAUNA = 'Fauna', 'Fauna'
    WEED = 'Weed', 'Weed'
    NOTE = 'Note', 'Note'

class IssueStatusEnum(models.TextChoices):
    FIXED = 'Fixed', 'Fixed'
    NEEDS_WORK = 'NeedsWork', 'Needs Work'
    PROGRESSING = 'Progressing', 'Progressing'
    NEEDS_REPEATING = 'NeedsRepeating', 'Needs Repeating'
    NO_ACTION_REQ = 'NoActionReq', 'No action req.'

class AuditActionEnum(models.TextChoices):
    LOGIN = 'Login', 'Login'
    LOGOUT = 'Logout', 'Logout'
    LOGIN_FAILED = 'LoginFailed', 'Login Failed'

class Line(models.Model):
    class Meta:
        ordering = ['name'] # Orders by 'name' in ascending order
    name = models.CharField(max_length=100)
    line_type = models.CharField(max_length=20, choices=LineType.choices)
    start_station_id = models.CharField(max_length=5)
    end_station_id = models.CharField(max_length=5)

    def __str__(self):
        return f"{self.name} ({self.get_line_type_display()})"

class TeamMember(models.Model):
    name = models.CharField(max_length=15)
    available = models.BooleanField(default=True)

    def __str__(self):
        return self.name if self.available else f'[{self.name}]'

    class Meta:
        ordering = ['-available', 'name']

class Outing(models.Model):
    date = models.DateField()
    hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Total hours worked during this outing"
    )
    number_of_workers = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        validators=[MinValueValidator(0)],
        default=1,
        help_text="Number of workers (can be decimal, e.g., 2.5 if someone left early)"
    )
    participants = models.ManyToManyField(
        TeamMember,
        blank=True,
        help_text="Specific team members who participated (if known)"
    )
    route = models.ForeignKey(Line, on_delete=models.CASCADE, related_name='outings')
    completion_status = models.CharField(
        max_length=20,
        choices=CompletionStatus.choices,
        default=CompletionStatus.COMPLETED
    )
    start_station_id = models.CharField(
        max_length=5,
        blank=True,
        null=True,
        help_text="Starting station ID for this outing (subset of the line)"
    )
    end_station_id = models.CharField(
        max_length=5,
        blank=True,
        null=True,
        help_text="Ending station ID for this outing (subset of the line)"
    )

    def __str__(self):
        return f"Outing on {self.date} - {self.get_completion_status_display()}"

class Issue(models.Model):
    issue_status = models.CharField(max_length=20, choices=IssueStatusEnum.choices, default=IssueStatusEnum.NEEDS_WORK)
    line = models.ForeignKey(Line, on_delete=models.CASCADE, related_name='issues')

    start_station_id = models.CharField(max_length=5)
    end_station_id = models.CharField(max_length=5, blank=True, null=True)
    station_type = models.CharField(max_length=20, choices=StationType.choices, default=StationType.NA)
    issue_type = models.CharField(max_length=20, choices=IssueEnum.choices)
    origin = models.CharField(max_length=15, blank=True, null=True)
    reported_by = models.CharField(max_length=10, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    photo = models.ImageField(upload_to='issue_photos/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    outing = models.ForeignKey(
        Outing,
        on_delete=models.CASCADE,
        related_name='issues',
        null=True,
        blank=True,
        help_text="The outing during which this issue was found (optional)"
    )

    def __str__(self):
        return f"Issue at {self.start_station_id}: {self.get_issue_type_display()}"

class CompletionReport(Line):
    """
    Proxy model for displaying the Completion Report in the admin sidebar
    """
    class Meta:
        proxy = True
        verbose_name = "Completion Report"
        verbose_name_plural = "Completion Report"

class Audit(models.Model):
    action = models.CharField(max_length=20, choices=AuditActionEnum.choices)
    ip = models.GenericIPAddressField(null=True)
    username = models.CharField(max_length=256, null=True)
    when = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "User Login Activity"
        verbose_name_plural = "User Login Activities"

@receiver(user_logged_in)
def user_logged_in_callback(sender, request, user, **kwargs):
    ip = request.META.get('REMOTE_ADDR')
    Audit.objects.create(action=AuditActionEnum.LOGIN, ip=ip, username=user.username)

@receiver(user_logged_out)
def user_logged_out_callback(sender, request, user, **kwargs):
    ip = request.META.get('REMOTE_ADDR')
    Audit.objects.create(action=AuditActionEnum.LOGOUT, ip=ip, username=user.username)

@receiver(user_login_failed)
def user_login_failed_callback(sender, request, credentials, **kwargs):
    ip = request.META.get('REMOTE_ADDR')
    username = credentials.get('username', None)
    Audit.objects.create(action=AuditActionEnum.LOGIN_FAILED, ip=ip, username=username)
