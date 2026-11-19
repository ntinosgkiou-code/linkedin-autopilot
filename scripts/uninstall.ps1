# Removes the scheduled tasks. Your data\ folder is kept.
foreach ($n in 'Outreach', 'Inbox', 'Post') {
    Unregister-ScheduledTask -TaskName $n -TaskPath '\LinkedInAutopilot\' -Confirm:$false -ErrorAction SilentlyContinue
}
Write-Host 'Scheduled tasks removed. To also sign out of LinkedIn:  uvx mcp-server-linkedin --logout'
