from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

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
    MISSING_WIRE = 'MissingWire', 'Missing Wire'
    SLIGHTLY_ROTTEN = 'SlightlyRotten', 'Slightly Rotten'
    VERY_ROTTEN = 'VeryRotten', 'Very Rotten'
    NEEDS_CLEARING = 'NeedsClearing', 'Needs Clearing'
    NEEDS_REPLACING = 'NeedsReplacing', 'Needs Replacing'
    NEEDS_ROPE = 'NeedsRope', 'Needs Rope'
    NEEDS_FREQUENT_ATTN = 'NeedsFrequentAttn', 'Needs Frequent Attention'
    ROPE_ON_DEAD_TREE = 'RopeOnDeadTree', 'Rope On Dead Tree'
    REQUIRES_CHAINSAW = 'RequiresChainsaw', 'Requires Chainsaw'
    FLORA = 'Flora', 'Flora'
    FAUNA = 'Fauna', 'Fauna'
    WEED = 'Weed', 'Weed'

class IssueStatusEnum(models.TextChoices):
    FIXED = 'Fixed', 'Fixed'
    NEEDS_WORK = 'NeedsWork', 'Needs Work'
    PROGRESSING = 'Progressing', 'Progressing'
    NEEDS_REPEATING = 'NeedsRepeating', 'Needs Repeating'
    NOTICE = 'Notice', 'Notice (no action req.)'

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
    name = models.CharField(max_length=100)
    email_address = models.EmailField()

    def __str__(self):
        return self.name

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
    last_action_date = models.DateField(null=True, blank=True)
    line = models.ForeignKey(Line, on_delete=models.CASCADE, related_name='issues')

    start_station_id = models.CharField(max_length=5)
    end_station_id = models.CharField(max_length=5, blank=True, null=True)
    station_type = models.CharField(max_length=20, choices=StationType.choices, default=StationType.NA)
    issue_type = models.CharField(max_length=20, choices=IssueEnum.choices)
    description = models.TextField(blank=True, null=True)
    photo = models.ImageField(upload_to='issue_photos/', blank=True, null=True)
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
