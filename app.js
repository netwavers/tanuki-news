/* ==========================================================================
   🐾 Frontend logic for たぬきちゃんのイチオシニュース (app.js)
   ========================================================================== */

document.addEventListener('DOMContentLoaded', () => {
  // Global States
  let allNews = [];
  let currentCategory = 'ALL';
  let searchQuery = '';

  // DOM Elements
  const newsContainer = document.getElementById('news-cards-container');
  const searchInput = document.getElementById('search-input');
  const clearSearchBtn = document.getElementById('clear-search-btn');
  const filterTabs = document.querySelectorAll('.filter-tab');
  const newsCountText = document.getElementById('news-count-text');
  const refreshIndicator = document.getElementById('last-update-indicator');
  const refreshIcon = document.getElementById('refresh-icon');

  // Fetch News Data from JSON
  async function fetchNews() {
    try {
      showLoading();
      // キャッシュ無効化のためのクエリパラメータを付与
      const response = await fetch('news.json?t=' + new Date().getTime());
      if (!response.ok) {
        throw new Error('JSONデータの取得に失敗しましたわ。');
      }
      allNews = await response.json();
      
      // データ更新日の取得と表示（最新ニュースの日付、あるいは現在時刻）
      updateLastRefreshed();
      renderNews();
    } catch (error) {
      console.error(error);
      showError(error.message);
    }
  }

  // Render News Items
  function renderNews() {
    newsContainer.innerHTML = '';

    // Filter Logic
    const filteredNews = allNews.filter(item => {
      const matchesCategory = currentCategory === 'ALL' || item.category === currentCategory;
      const matchesSearch = searchQuery === '' || 
        item.title.toLowerCase().includes(searchQuery) ||
        (item.comment && item.comment.toLowerCase().includes(searchQuery));
      return matchesCategory && matchesSearch;
    });

    // Count Update
    newsCountText.textContent = `ご主人様、本日は該当ニュースが ${filteredNews.length} 件ありますわ！`;

    if (filteredNews.length === 0) {
      showEmptyState();
      return;
    }

    // Build Cards
    filteredNews.forEach(item => {
      const card = document.createElement('article');
      card.className = 'news-card';
      
      // 星評価生成 (1〜5)
      const score = item.score || 4;
      let starsHtml = '';
      for (let i = 0; i < 5; i++) {
        if (i < score) {
          starsHtml += '<i class="fa-solid fa-star"></i>';
        } else {
          starsHtml += '<i class="fa-regular fa-star"></i>';
        }
      }

      // 日付のフォーマット
      const formattedDate = formatDate(item.published_at);

      card.innerHTML = `
        <div class="card-meta">
          <div class="badge-group">
            <span class="badge badge-category">${item.category}</span>
            <span class="badge badge-source">${item.source}</span>
          </div>
          <span class="pub-date">${formattedDate}</span>
        </div>
        
        <h2 class="news-card-title">
          <a href="${item.url}" target="_blank" rel="noopener noreferrer" title="${item.title}">
            ${item.title}
            <i class="fa-solid fa-up-right-from-square link-icon"></i>
          </a>
        </h2>

        <div class="score-stars" aria-label="おすすめ度: ${score}点">
          ${starsHtml}
        </div>

        <div class="tanuki-comment-container">
          <img src="assets/tanuki_avatar.png" alt="たぬきちゃん" class="tanuki-comment-avatar">
          <div class="speech-bubble">
            <div class="speech-bubble-name">たぬきちゃんのイチオシコメント</div>
            <div class="speech-bubble-text">${item.comment || 'ご主人様、こちらのニュースは特におすすめですわ！'}</div>
          </div>
        </div>
      `;
      newsContainer.appendChild(card);
    });
  }

  // Format date to readable local time
  function formatDate(dateStr) {
    try {
      const date = new Date(dateStr);
      if (isNaN(date.getTime())) {
        return dateStr; // パースに失敗した場合はそのまま表示
      }
      return `${date.getFullYear()}年${(date.getMonth() + 1)}月${date.getDate()}日 ${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
    } catch (e) {
      return dateStr;
    }
  }

  // Update Status Bar info
  function updateLastRefreshed() {
    refreshIcon.classList.remove('spinner');
    const now = new Date();
    refreshIndicator.innerHTML = `<i class="fa-solid fa-check"></i> 最新の状態で表示中ですわ (${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')})`;
  }

  // Loading indicator
  function showLoading() {
    refreshIcon.classList.add('spinner');
    newsContainer.innerHTML = `
      <div class="loading-state">
        <i class="fa-solid fa-circle-notch fa-spin loading-spinner"></i>
        <p>ニュースをお取り寄せ中ですので、少々お待ちくださいませ...</p>
      </div>
    `;
  }

  // Error screen
  function showError(msg) {
    refreshIcon.classList.remove('spinner');
    refreshIndicator.innerHTML = `<i class="fa-solid fa-circle-exclamation" style="color: var(--accent-color);"></i> 読み込みエラー`;
    newsContainer.innerHTML = `
      <div class="empty-state">
        <i class="fa-solid fa-triangle-exclamation" style="color: var(--accent-color);"></i>
        <p>申し訳ありません、ご主人様。ニュースの取得中にエラーが発生しましたわ。</p>
        <p style="font-size: 0.85rem; font-weight: normal; margin-top: 8px;">エラー詳細: ${msg}</p>
      </div>
    `;
  }

  // Empty Search/Filter results
  function showEmptyState() {
    newsContainer.innerHTML = `
      <div class="empty-state">
        <i class="fa-regular fa-folder-open"></i>
        <p>ご主人様、ご指定の条件に合うニュースが見つかりませんでしたわ...</p>
      </div>
    `;
  }

  // ==========================================================================
  // Event Listeners
  // ==========================================================================

  // Search Input Handle
  searchInput.addEventListener('input', (e) => {
    searchQuery = e.target.value.toLowerCase().trim();
    if (searchQuery.length > 0) {
      clearSearchBtn.style.display = 'block';
    } else {
      clearSearchBtn.style.display = 'none';
    }
    renderNews();
  });

  // Clear Search Input
  clearSearchBtn.addEventListener('click', () => {
    searchInput.value = '';
    searchQuery = '';
    clearSearchBtn.style.display = 'none';
    searchInput.focus();
    renderNews();
  });

  // Filter Tabs Event Handle
  filterTabs.forEach(tab => {
    tab.addEventListener('click', (e) => {
      // Remove active from all
      filterTabs.forEach(t => {
        t.classList.remove('active');
        t.setAttribute('aria-selected', 'false');
      });

      // Add active to current
      const selectedTab = e.currentTarget;
      selectedTab.classList.add('active');
      selectedTab.setAttribute('aria-selected', 'true');

      // Update State
      currentCategory = selectedTab.getAttribute('data-category');
      renderNews();
    });
  });

  // Initial Action
  fetchNews();
});
