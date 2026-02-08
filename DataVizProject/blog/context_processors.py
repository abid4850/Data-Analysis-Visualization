from .models import Blog

def latest_blogs(request):
    blogs = Blog.objects.order_by('-created_at')[:5]  # latest 5 posts
    return {'latest_blogs': blogs}
