<?php
// Load global configuration, translations, and database model
require_once 'config.php';
require_once 'PensionnairesModel.php';

$model = new PensionnairesModel();

// Retrieve search, filter, and sorting parameters from the URL
$searchQuery = $_GET['q'] ?? '';
$deptFilter = $_GET['dept'] ?? '';
$sort = $_GET['sort'] ?? 'alpha';

// Fetch global statistics for the current search criteria
$stats = $model->getStats($searchQuery, $deptFilter);
$totalPensionnaires = $stats['count'];
$totalLivres = $stats['amount'];
$limit = 50;
$totalPages = ceil($totalPensionnaires / $limit);

// Ensure the requested page falls within valid boundaries
$requestedPage = isset($_GET['page']) ? (int)$_GET['page'] : 1;
if ($totalPages > 0) {
    $page = max(1, min($requestedPage, $totalPages));
} else {
    $page = 1;
}

// Calculate pagination offset and fetch the corresponding results
$offset = ($page - 1) * $limit;
$results = $model->search($searchQuery, $deptFilter, $sort, $limit, $offset);

// Preserve URL parameters for pagination links, excluding the current page number
$queryParams = $_GET;
unset($queryParams['page']);
$urlParams = !empty($queryParams) ? '&' . http_build_query($queryParams) : '';

// Extract and map the department to a specific UI badge from JSON data
function getBadgeDept($pensionsJson) {
    if (empty($pensionsJson)) return null;
    $pensions = json_decode($pensionsJson, true);
    if (is_array($pensions) && !empty($pensions)) {
        foreach ($pensions as $p) {
            if (isset($p['department'])) {
                switch (strtolower($p['department'])) {
                    case 'finances': return ['tag' => 'badge-f', 'label' => 'F'];
                    case 'guerre': return ['tag' => 'badge-g', 'label' => 'G'];
                    case 'marine': return ['tag' => 'badge-m', 'label' => 'M'];
                    case 'affaires étrangères': return ['tag' => 'badge-afe', 'label' => 'Af. É.'];
                    case 'maison du roi': return ['tag' => 'badge-mdur', 'label' => 'M. du R.'];
                }
            }
        }
    }
    return null;
}

// Extract the primary job title, falling back to detailed pension data if necessary
function getJobTitle($jobsJson, $pensionsJson) {
    $jobs = json_decode($jobsJson, true);
    if (is_array($jobs) && !empty($jobs) && isset($jobs[0]['title'])) {
        return ucfirst($jobs[0]['title']);
    }
    $pensions = json_decode($pensionsJson, true);
    if (is_array($pensions) && !empty($pensions) && isset($pensions[0]['jobs'][0]['title'])) {
        return ucfirst($pensions[0]['jobs'][0]['title']);
    }
    return 'Pensionnaire';
}

// Concatenate detailed pension texts to form a complete description
function getDescription($pensionsJson, $fallback) {
    $pensions = json_decode($pensionsJson, true);
    if (is_array($pensions) && !empty($pensions)) {
        $texts = [];
        foreach ($pensions as $p) {
            if (!empty($p['text'])) {
                $texts[] = $p['text'];
            }
        }
        if (!empty($texts)) {
            return htmlspecialchars(implode(' ', $texts));
        }
    }
    return htmlspecialchars($fallback);
}
?>
<!DOCTYPE html>
<html lang="<?= $currentLang ?>">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pensionnaires - <?= msg('nav_search') ?></title>
    <link rel="stylesheet" href="css/global.css">
    <link rel="stylesheet" href="css/index.css">
</head>
<body>
    <header>
        <a href="index.php" class="logo">Pensionnaires</a>
        <nav>
            <a href="index.php" class="active"><?= msg('nav_search') ?></a>
            <a href="advancedSearch.php"><?= msg('nav_advanced') ?></a>
            <a href="sources.php"><?= msg('nav_sources') ?></a>
        </nav>
        
        <!-- Language switcher preserving current search parameters -->
        <div class="lang-switcher">
            <?php 
            $qParams = $_GET;
            $qParams['lang'] = 'fr';
            $urlFr = '?' . http_build_query($qParams);
            
            $qParams['lang'] = 'en';
            $urlEn = '?' . http_build_query($qParams);
            ?>
            <a href="<?= $urlFr ?>" class="<?= $currentLang === 'fr' ? 'active' : '' ?>">
                <img src="img/fr.png" alt="Français">
            </a>
            <a href="<?= $urlEn ?>" class="<?= $currentLang === 'en' ? 'active' : '' ?>">
                <img src="img/en.png" alt="English">
            </a>
        </div>
    </header>

    <main>
        <!-- Hero section with search form and global statistics -->
        <section class="hero">
            <h1><?= msg('hero_title') ?></h1>
            <p><?= msg('hero_subtitle') ?><br><br>
            <?= msg('hero_desc') ?></p>
            
            <div class="search-container">
                <form action="index.php" method="GET" class="search-form">
                    <input type="text" name="q" placeholder="<?= msg('search_placeholder') ?>" value="<?= htmlspecialchars($searchQuery) ?>">
                    <?php if(!empty($deptFilter)): ?>
                        <input type="hidden" name="dept" value="<?= htmlspecialchars($deptFilter) ?>">
                    <?php endif; ?>
                </form>
                <a href="advancedSearch.php" class="btn-advanced"><?= msg('search_btn_adv') ?></a>
            </div>

            <div class="stats">
                <div class="stat-item">
                    <strong><?= number_format($totalPensionnaires, 0, ',', ' ') ?></strong>
                    <span><?= msg('stat_pensioners') ?></span>
                </div>
                <div class="stat-item">
                    <strong><?= $totalLivres ?></strong>
                    <span><?= msg('stat_amount') ?></span>
                </div>
            </div>
        </section>

        <!-- Department filters -->
        <section class="filters-bar">
            <div class="filter-tags">
                <span><?= msg('filter_dept') ?></span>
                <a href="?q=<?= urlencode($searchQuery) ?>" class="tag-btn t-all <?= empty($deptFilter) ? 'active' : '' ?>"><?= msg('filter_all') ?></a>
                <a href="?q=<?= urlencode($searchQuery) ?>&dept=Guerre" class="tag-btn t-g <?= $deptFilter === 'Guerre' ? 'active' : '' ?>"><?= msg('filter_war') ?></a>
                <a href="?q=<?= urlencode($searchQuery) ?>&dept=Marine" class="tag-btn t-m <?= $deptFilter === 'Marine' ? 'active' : '' ?>"><?= msg('filter_navy') ?></a>
                <a href="?q=<?= urlencode($searchQuery) ?>&dept=Finances" class="tag-btn t-f <?= $deptFilter === 'Finances' ? 'active' : '' ?>"><?= msg('filter_finance') ?></a>
                <a href="?q=<?= urlencode($searchQuery) ?>&dept=Maison du Roi" class="tag-btn t-mdur <?= $deptFilter === 'Maison du Roi' ? 'active' : '' ?>"><?= msg('filter_house') ?></a>
            </div>
        </section>

        <!-- Results listing and sorting -->
        <section class="results-container">
            <div class="results-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
                <div style="display: flex; align-items: center; gap: 1rem;">
                    <span style="color: var(--text-muted); font-size: 0.85rem;"><?= count($results) ?> <?= msg('results_count') ?> <?= !empty($deptFilter) ? '- ' . htmlspecialchars($deptFilter) : '' ?></span>
                    
                    <form action="" method="GET" style="display: flex; align-items: center; gap: 0.5rem;">
                        <input type="hidden" name="q" value="<?= htmlspecialchars($searchQuery) ?>">
                        <?php if(!empty($deptFilter)): ?>
                            <input type="hidden" name="dept" value="<?= htmlspecialchars($deptFilter) ?>">
                        <?php endif; ?>
                        
                        <label for="sort-index" style="font-size: 0.85rem; color: var(--text-muted);"><?= msg('sort_label') ?></label>
                        <select name="sort" id="sort-index" onchange="this.form.submit()" style="padding: 0.3rem; border: 1px solid var(--border-color); border-radius: 4px; font-size: 0.85rem; font-family: var(--font-sans); color: var(--text-main);">
                            <option value="alpha" <?= $sort === 'alpha' ? 'selected' : '' ?>><?= msg('sort_alpha') ?></option>
                            <option value="amount_desc" <?= $sort === 'amount_desc' ? 'selected' : '' ?>><?= msg('sort_desc') ?></option>
                            <option value="amount_asc" <?= $sort === 'amount_asc' ? 'selected' : '' ?>><?= msg('sort_asc') ?></option>
                        </select>
                    </form>
                </div>
                
                <?php if(!empty($searchQuery) || !empty($deptFilter) || $sort !== 'alpha'): ?>
                    <a href="index.php" style="font-size: 0.85rem; color: var(--text-muted);"><?= msg('btn_reset') ?></a>
                <?php endif; ?>
            </div>

            <?php if(empty($results)): ?>
                <p style="text-align:center; color: var(--text-muted); margin-top: 2rem;"><?= msg('no_results') ?></p>
            <?php else: ?>
                <?php 
                $count = $offset + 1;
                // Render each pensioner card dynamically
                foreach($results as $row): 
                    $nom = htmlspecialchars($row['last_name'] ?? 'Inconnu');
                    $prenom = htmlspecialchars($row['first_name'] ?? '');
                    $age = $row['age'] ? $row['age'] . ' ' . msg('age_years') : msg('age_unknown');
                    $montant = number_format($row['total_amount'] ?? 0, 0, ',', ' ') . ' L';
                    
                    $titre = getJobTitle($row['jobs'], $row['detailed_pensions']);
                    $badge = getBadgeDept($row['detailed_pensions']);
                    $desc = getDescription($row['detailed_pensions'], $row['identity_text'] ?? '');
                ?>
                <a href="pensionnaire.php?id=<?= $row['id'] ?>" class="result-card">
                    <div class="result-id"><?= sprintf('%02d', $count++) ?></div>
                    
                    <div class="result-content">
                        <div class="result-top">
                            <div class="result-name">
                                <strong><?= $nom ?></strong> <?= $prenom ?>
                                <?php if($badge): ?>
                                    <span class="badge <?= $badge['tag'] ?>"><?= $badge['label'] ?></span>
                                <?php endif; ?>
                            </div>
                            <div class="result-meta">
                                <span class="result-amount"><?= $montant ?></span>
                                <span class="result-age"><?= $age ?></span>
                            </div>
                        </div>
                        <div class="result-subtitle"><?= htmlspecialchars($titre) ?></div>
                        <div class="result-desc"><?= $desc ?></div>
                    </div>
                </a>
                <?php endforeach; ?>
            <?php endif; ?>
            
            <!-- Sliding window pagination with direct page input -->
            <?php if ($totalPages > 1): ?>
                <div class="pagination">
                    <?php 
                    $startPage = max(1, $page - 1);
                    $endPage = min($totalPages, $page + 1);
                    
                    if ($page == 1 && $totalPages >= 3) {
                        $endPage = 3;
                    }
                    if ($page == $totalPages && $totalPages >= 3) {
                        $startPage = $totalPages - 2;
                    }

                    for($i = $startPage; $i <= $endPage; $i++): 
                    ?>
                        <a href="?page=<?=$i?><?=$urlParams?>" class="page-link <?=$i === $page ? 'active' : ''?>"><?=$i?></a>
                    <?php endfor; ?>
                    
                    <?php if ($endPage < $totalPages): ?>
                        <?php if ($endPage < $totalPages - 1): ?>
                            <span style="display:flex; align-items:flex-end; padding:0 0.2rem; color:var(--text-muted)">...</span>
                        <?php endif; ?>
                        <a href="?page=<?=$totalPages?><?=$urlParams?>" class="page-link"><?=$totalPages?></a>
                    <?php endif; ?>
                    
                    <?php if ($totalPages > 3): ?>
                        <form action="" method="GET" class="pagination-form" style="margin-left: 0.5rem;">
                            <?php 
                            foreach ($queryParams as $key => $val) {
                                if (is_array($val)) {
                                    foreach ($val as $v) {
                                        echo '<input type="hidden" name="'.htmlspecialchars($key).'[]" value="'.htmlspecialchars($v).'">';
                                    }
                                } else {
                                    echo '<input type="hidden" name="'.htmlspecialchars($key).'" value="'.htmlspecialchars($val).'">';
                                }
                            }
                            ?>
                            <input type="number" name="page" min="1" max="<?=$totalPages?>" value="" placeholder="N°" class="page-input" aria-label="Numéro de page">
                            <button type="submit" class="page-btn"><?= msg('btn_go') ?></button>
                        </form>
                    <?php endif; ?>
                </div>
            <?php endif; ?>
        </section>
    </main>
    <footer><a href="#"><?= msg('footer_legal') ?></a></footer>
</body>
</html>