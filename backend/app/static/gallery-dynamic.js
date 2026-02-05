// Dynamic Gallery Integration with /gallery API endpoint
// Supports cursor pagination, location filters, and featured items

class VejaProGallery {
  constructor(containerId, options = {}) {
    this.container = document.getElementById(containerId);
    this.options = {
      limit: options.limit || 24,
      apiEndpoint: options.apiEndpoint || '/api/v1/gallery',
      locationFilter: options.locationFilter || null,
      featuredOnly: options.featuredOnly || false,
      ...options
    };
    
    this.cursor = null;
    this.hasMore = true;
    this.loading = false;
    this.items = [];
  }

  async fetchGallery() {
    if (this.loading || !this.hasMore) return;
    
    this.loading = true;
    this.showLoader();

    try {
      const params = new URLSearchParams({
        limit: this.options.limit
      });
      
      if (this.cursor) params.append('cursor', this.cursor);
      if (this.options.locationFilter) params.append('location_tag', this.options.locationFilter);
      if (this.options.featuredOnly) params.append('featured_only', 'true');

      const response = await fetch(`${this.options.apiEndpoint}?${params}`);
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const data = await response.json();
      
      this.items = [...this.items, ...data.items];
      this.cursor = data.next_cursor;
      this.hasMore = data.has_more;
      
      this.renderItems(data.items);
      
    } catch (error) {
      console.error('Gallery fetch error:', error);
      this.showError('Nepavyko užkrauti galerijos. Bandykite vėliau.');
    } finally {
      this.loading = false;
      this.hideLoader();
    }
  }

  renderItems(items) {
    const fragment = document.createDocumentFragment();
    
    items.forEach(item => {
      const card = this.createGalleryCard(item);
      fragment.appendChild(card);
    });
    
    const grid = this.container.querySelector('.photo-grid') || this.createGrid();
    grid.appendChild(fragment);
  }

  createGrid() {
    const grid = document.createElement('div');
    grid.className = 'photo-grid';
    this.container.appendChild(grid);
    return grid;
  }

  createGalleryCard(item) {
    const card = document.createElement('div');
    card.className = 'photo-card';
    card.style.cursor = 'pointer';
    
    const img = document.createElement('img');
    img.src = item.file_url;
    img.alt = item.location_tag || 'VejaPRO projektas';
    img.loading = 'lazy';
    
    card.appendChild(img);
    
    if (item.is_featured) {
      const badge = document.createElement('div');
      badge.className = 'featured-badge';
      badge.textContent = '⭐ Išskirtinis';
      badge.style.cssText = `
        position: absolute;
        top: 12px;
        right: 12px;
        background: rgba(47, 107, 79, 0.95);
        color: white;
        padding: 6px 12px;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: 600;
      `;
      card.style.position = 'relative';
      card.appendChild(badge);
    }
    
    if (item.location_tag) {
      const location = document.createElement('div');
      location.className = 'location-tag';
      location.textContent = item.location_tag;
      location.style.cssText = `
        position: absolute;
        bottom: 12px;
        left: 12px;
        background: rgba(255, 255, 255, 0.95);
        padding: 6px 12px;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: 600;
      `;
      card.style.position = 'relative';
      card.appendChild(location);
    }
    
    card.addEventListener('click', () => this.openLightbox(item));
    
    return card;
  }

  openLightbox(item) {
    // Simple lightbox implementation
    const lightbox = document.createElement('div');
    lightbox.className = 'lightbox';
    lightbox.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0, 0, 0, 0.9);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 9999;
      cursor: pointer;
    `;
    
    const img = document.createElement('img');
    img.src = item.file_url;
    img.style.cssText = `
      max-width: 90%;
      max-height: 90%;
      border-radius: 12px;
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
    `;
    
    lightbox.appendChild(img);
    lightbox.addEventListener('click', () => lightbox.remove());
    
    document.body.appendChild(lightbox);
  }

  showLoader() {
    const loader = document.createElement('div');
    loader.id = 'gallery-loader';
    loader.style.cssText = `
      text-align: center;
      padding: 40px;
      color: var(--muted);
    `;
    loader.innerHTML = '<div style="font-size: 1.2rem;">⏳ Kraunama...</div>';
    this.container.appendChild(loader);
  }

  hideLoader() {
    const loader = document.getElementById('gallery-loader');
    if (loader) loader.remove();
  }

  showError(message) {
    const error = document.createElement('div');
    error.style.cssText = `
      padding: 20px;
      background: rgba(220, 38, 38, 0.1);
      border: 1px solid rgba(220, 38, 38, 0.3);
      border-radius: 12px;
      color: #991b1b;
      text-align: center;
      margin: 20px 0;
    `;
    error.textContent = message;
    this.container.appendChild(error);
  }

  setupInfiniteScroll() {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting && this.hasMore && !this.loading) {
          this.fetchGallery();
        }
      });
    }, { threshold: 0.5 });

    const sentinel = document.createElement('div');
    sentinel.id = 'scroll-sentinel';
    sentinel.style.height = '1px';
    this.container.appendChild(sentinel);
    observer.observe(sentinel);
  }

  init() {
    this.fetchGallery();
    this.setupInfiniteScroll();
  }
}

// Export for use in landing page
window.VejaProGallery = VejaProGallery;
