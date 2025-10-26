from django.db import models
from users.models import User

class Notification(models.Model):
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    sender = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sent_notifications')
    
    title = models.CharField(max_length=255)
    message = models.TextField()
    notification_type = models.CharField(max_length=50)
    action_url = models.URLField(blank=True, null=True)

    target_role = models.CharField(max_length=32, blank=True, null=True)  # ✅ ADD THIS LINE

    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} → {self.recipient or self.target_role}"
    
    def __str__(self):
        return f"Notification to {self.recipient.username}: {self.title}"

    class Meta:
        ordering = ['-created_at']