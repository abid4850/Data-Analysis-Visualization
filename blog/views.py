from django.shortcuts import render, get_object_or_404
from .models import Blog

def blog_list(request):
    posts = Blog.objects.all()
    return render(request, 'blog/blog_list.html', {'posts': posts})

def blog_detail(request, slug):
    post = get_object_or_404(Blog, slug=slug)
    return render(request, 'blog/blog_detail.html', {'post': post})
