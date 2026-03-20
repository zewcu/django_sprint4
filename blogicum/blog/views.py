from django.shortcuts import (
    render,
    redirect,
    get_object_or_404
)
from django.views.generic import (
    ListView,
    DetailView,
    CreateView,
    UpdateView,
    DeleteView
)
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.db.models import Count
from .models import Post, Category, Comment
from .forms import CommentForm, PostForm
from django.core.paginator import Paginator
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserChangeForm


def get_published_posts(queryset=None):
    """
    Фильтрует посты по критериям опубликованности
    """
    if queryset is None:
        queryset = Post.objects.all()
    return queryset.filter(
        is_published=True,
        category__is_published=True,
        pub_date__lte=timezone.now()
    )


def get_posts_with_comments(queryset=None, filter_published=True):
    """
    Дополняет посты количеством комментариев и опционально фильтрует по опубликованности
    """
    if queryset is None:
        queryset = Post.objects.all()
    
    queryset = queryset.select_related('author', 'location', 'category')
    queryset = queryset.annotate(comment_count=Count('comments'))
    
    if filter_published:
        queryset = get_published_posts(queryset)
    
    if Post._meta.ordering:
        queryset = queryset.order_by(*Post._meta.ordering)
    else:
        queryset = queryset.order_by('-pub_date')
    
    return queryset


def get_page_obj(request, queryset, per_page=10):
    """
    Возвращает объект страницы пагинатора для заданного queryset
    """
    paginator = Paginator(queryset, per_page)
    page_number = request.GET.get('page')
    return paginator.get_page(page_number)


class IndexView(ListView):
    model = Post
    template_name = 'blog/index.html'
    paginate_by = 10
    context_object_name = 'post_list'

    def get_queryset(self):
        return get_posts_with_comments(filter_published=True)


def post_detail(request, id):
    post = get_object_or_404(
        Post.objects.select_related('category', 'location', 'author'),
        id=id,
        is_published=True,
        category__is_published=True,
        pub_date__lte=timezone.now()
    )
    context = {'post': post}
    return render(request, 'blog/detail.html', context)


def category_posts(request, category_slug):
    category = get_object_or_404(
        Category,
        slug=category_slug,
        is_published=True
    )
    post_list = Post.objects.select_related(
        'category', 'location', 'author'
    ).filter(
        category=category,
        is_published=True,
        pub_date__lte=timezone.now()
    ).order_by('-pub_date')

    context = {'category': category, 'post_list': post_list}
    return render(request, 'blog/category.html', context)


class PostCreateView(LoginRequiredMixin, CreateView):
    model = Post
    template_name = 'blog/create.html'
    form_class = PostForm

    def form_valid(self, form):
        form.instance.author = self.request.user
        form.save()
        return redirect('blog:profile', username=self.request.user.username)


class PostUpdateView(LoginRequiredMixin, UpdateView):
    model = Post
    template_name = 'blog/create.html'
    form_class = PostForm
    pk_url_kwarg = 'post_id'

    def dispatch(self, request, *args, **kwargs):
        instance = get_object_or_404(Post, pk=kwargs['post_id'])
        if instance.author != request.user:
            return redirect('blog:post_detail', post_id=kwargs['post_id'])
        return super().dispatch(request, *args, **kwargs)


class PostDeleteView(LoginRequiredMixin, DeleteView):
    model = Post
    success_url = reverse_lazy('blog:index')
    pk_url_kwarg = 'post_id'

    def dispatch(self, request, *args, **kwargs):
        instance = get_object_or_404(Post, pk=kwargs['post_id'])
        if instance.author != request.user:
            return redirect('blog:post_detail', post_id=kwargs['post_id'])
        return super().dispatch(request, *args, **kwargs)


class CategoryPostView(ListView):
    template_name = 'blog/category.html'
    context_object_name = 'post_list'
    paginate_by = 10

    def get_queryset(self):
        category_slug = self.kwargs['category_slug']
        self.category = get_object_or_404(
            Category, slug=category_slug, is_published=True)
        posts = self.category.post_set.all()
        return get_posts_with_comments(posts, filter_published=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['category'] = self.category
        return context


class ProfileView(DetailView):
    model = get_user_model()
    template_name = 'blog/profile.html'
    slug_field = 'username'
    slug_url_kwarg = 'username'
    context_object_name = 'profile'

    def get_object(self, queryset=None):
        return get_object_or_404(
            get_user_model(),
            username=self.kwargs['username'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile_user = self.get_object()
        posts = profile_user.posts.all()
        filter_published = self.request.user != profile_user
        posts = get_posts_with_comments(posts, filter_published=filter_published)
        context['page_obj'] = get_page_obj(self.request, posts, 10)
        return context


class PostDetailView(DetailView):
    model = Post
    template_name = 'blog/detail.html'
    pk_url_kwarg = 'post_id'

    def get_queryset(self):
        if self.request.user.is_authenticated:
            return Post.objects.all()
        return Post.objects.filter(
            is_published=True,
            category__is_published=True,
            pub_date__lte=timezone.now()
        )

    def get_object(self, queryset=None):
        post = get_object_or_404(
            Post.objects.select_related('category', 'location', 'author'),
            pk=self.kwargs['post_id']
        )
        if (not self.request.user.is_authenticated
                or self.request.user != post.author):
            post = get_object_or_404(
                Post.objects.select_related('category', 'location', 'author'),
                pk=self.kwargs['post_id'],
                is_published=True,
                category__is_published=True,
                pub_date__lte=timezone.now()
            )
        return post

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = CommentForm()
        context['comments'] = self.object.comments.select_related('author')
        return context


class CommentCreateView(LoginRequiredMixin, CreateView):
    model = Comment
    form_class = CommentForm
    template_name = 'blog/comment.html'

    def form_valid(self, form):
        post = get_object_or_404(Post, pk=self.kwargs['post_id'])
        form.instance.author = self.request.user
        form.instance.post = post
        return super().form_valid(form)

    def get_success_url(self):
        return reverse(
            'blog:post_detail',
            kwargs={'post_id': self.kwargs['post_id']}
        )


class CommentUpdateView(LoginRequiredMixin, UpdateView):
    model = Comment
    template_name = 'blog/comment.html'
    pk_url_kwarg = 'comment_id'
    fields = ('text',)

    def dispatch(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.author != request.user:
            return redirect('blog:post_detail', post_id=instance.post.id)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse(
            'blog:post_detail', kwargs={
                'post_id': self.object.post.id})


class CommentDeleteView(LoginRequiredMixin, DeleteView):
    model = Comment
    template_name = 'blog/comment.html'
    pk_url_kwarg = 'comment_id'

    def dispatch(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.author != request.user:
            return redirect('blog:post_detail', post_id=instance.post.id)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return reverse(
            'blog:post_detail', kwargs={
                'post_id': self.object.post.id})


class ProfileUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = get_user_model()
    form_class = UserChangeForm
    template_name = 'blog/user_form.html'
    slug_field = 'username'
    slug_url_kwarg = 'username'

    def test_func(self):
        return self.request.user.username == self.kwargs['username']

    def get_success_url(self):
        return reverse(
            'blog:profile', kwargs={
                'username': self.kwargs['username']})

    def handle_no_permission(self):
        return redirect('blog:profile', username=self.kwargs['username'])


def page_not_found(request, exception):
    return render(request, 'pages/404.html', status=404)


def csrf_failure(request, reason=''):
    return render(request, 'pages/403csrf.html', status=403)


def server_error(request):
    return render(request, 'pages/500.html', status=500)
