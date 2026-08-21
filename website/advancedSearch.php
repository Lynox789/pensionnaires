<?php
//Load global configuration and database model
require_once 'config.php';
require_once 'PensionnairesModel.php';
$model = new PensionnairesModel();

//Extract form criteria from URL parameters
$fields = $_GET['fields'] ?? ['last_name'];
$values = $_GET['values'] ?? [''];

//Structure search criteria into an array of field-value pairs
$criteria = [];
for ($i = 0; $i < count($fields); $i++) {
    if (!empty(trim($values[$i]))) {
        $criteria[] = ['field' => $fields[$i], 'value' => $values[$i]];
    }
}

//Initialize pagination and sorting variables
$hasSearched = !empty($criteria);
$results = [];
$totalPensionnaires = 0;
$totalPages = 0;
$limit = 50;
$page = 1;
$sort = $_GET['sort'] ?? 'alpha';

//Process search if criteria are provided
if ($hasSearched) {
    $totalPensionnaires = $model->getAdvancedStats($criteria);
    $totalPages = ceil($totalPensionnaires / $limit);
    
    // Ensure the requested page falls within valid boundaries
    $requestedPage = isset($_GET['page']) ? (int)$_GET['page'] : 1;
    if ($totalPages > 0) {
        $page = max(1, min($requestedPage, $totalPages));
    } else {
        $page = 1;
    }
    
    //Calculate pagination offset and fetch results
    $offset = ($page - 1) * $limit;
    $results = $model->advancedSearch($criteria, $sort, $limit, $offset);
}

//Extract primary job title, falling back to detailed pension data if necessary
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
            if (!empty($p['text'])) $texts[] = $p['text'];
        }
        if (!empty($texts)) return htmlspecialchars(implode(' ', $texts));
    }
    return htmlspecialchars($fallback);
}

//Preserve URL parameters for pagination links, excluding the current page number
$queryParams = $_GET;
unset($queryParams['page']);
$urlParams = !empty($queryParams) ? '&' . http_build_query($queryParams) : '';

?>
<!DOCTYPE html>
<html lang="<?= $currentLang ?>">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?= msg('adv_title') ?> - Pensionnaires</title>
    <link rel="stylesheet" href="css/global.css">
    <link rel="stylesheet" href="css/index.css">
    <link rel="stylesheet" href="css/advancedSearch.css">
</head>
<body>
    <header>
        <a href="index.php" class="logo">Pensionnaires</a>
        <nav>
            <a href="index.php"><?= msg('nav_search') ?></a>
            <a href="advancedSearch.php" class="active"><?= msg('nav_advanced') ?></a>
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

    <div class="adv-search-hero">
        <h1><?= msg('adv_hero_title') ?></h1>
    </div>

    <main>
        <!-- Dynamic advanced search form container -->
        <div class="adv-container">
            <p class="adv-instructions">
                <?= msg('adv_instructions') ?>
            </p>

            <form action="advancedSearch.php" method="GET" id="adv-form">
                <div id="form-rows">
                    <?php for($i = 0; $i < max(1, count($fields)); $i++): ?>
                    <div class="adv-row">
                        <!-- Select dropdown for search fields -->
                        <select name="fields[]" class="adv-select">
                            <option value="last_name" <?= ($fields[$i] ?? '') === 'last_name' ? 'selected' : '' ?>><?= msg('adv_field_lastname') ?></option>
                            <option value="first_name" <?= ($fields[$i] ?? '') === 'first_name' ? 'selected' : '' ?>><?= msg('adv_field_firstname') ?></option>
                            <option value="sex" <?= ($fields[$i] ?? '') === 'sex' ? 'selected' : '' ?>><?= msg('adv_field_sex') ?></option>
                            <option value="birth_year" <?= ($fields[$i] ?? '') === 'birth_year' ? 'selected' : '' ?>><?= msg('adv_field_birth') ?></option>
                            <option value="department" <?= ($fields[$i] ?? '') === 'department' ? 'selected' : '' ?>><?= msg('adv_field_dept') ?></option>
                            <option value="class" <?= ($fields[$i] ?? '') === 'class' ? 'selected' : '' ?>><?= msg('adv_field_class') ?></option>
                        </select>
                        <input type="text" name="values[]" class="adv-input" placeholder="<?= msg('adv_placeholder_value') ?>" value="<?= htmlspecialchars($values[$i] ?? '') ?>">
                        <button type="button" class="adv-btn add-btn">+</button>
                        <!-- Remove button shown for rows subsequent to the first -->
                        <?php if($i > 0): ?>
                            <button type="button" class="adv-btn adv-btn-remove remove-btn">-</button>
                        <?php endif; ?>
                    </div>
                    <?php endfor; ?>
                </div>

                <div class="adv-submit-row">
                    <a href="index.php" class="simple-search-link"><?= msg('adv_link_simple') ?></a>
                    <button type="submit" class="adv-submit-btn"><?= msg('adv_btn_search') ?></button>
                </div>
            </form>
        </div>

        <!-- Render results section if a search was performed -->
        <?php if ($hasSearched): ?>
        <section class="results-container">
            <!-- Results header with result count and sorting options -->
            <div class="results-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.5rem;">
                <div style="display: flex; align-items: center; gap: 1rem;">
                    <span style="color: var(--text-muted); font-size: 0.85rem;"><?= $totalPensionnaires ?> <?= msg('results_count') ?></span>
                    
                    <form action="" method="GET" style="display: flex; align-items: center; gap: 0.5rem;">
                        <?php 
                        // Rebuild hidden inputs to maintain search criteria on sort change
                        foreach ($queryParams as $key => $val) {
                            if ($key === 'sort') continue;
                            if (is_array($val)) {
                                foreach ($val as $v) {
                                    echo '<input type="hidden" name="'.htmlspecialchars($key).'[]" value="'.htmlspecialchars($v).'">';
                                }
                            } else {
                                echo '<input type="hidden" name="'.htmlspecialchars($key).'" value="'.htmlspecialchars($val).'">';
                            }
                        }
                        ?>
                        <label for="sort-adv" style="font-size: 0.85rem; color: var(--text-muted);"><?= msg('sort_label') ?></label>
                        <select name="sort" id="sort-adv" onchange="this.form.submit()" style="padding: 0.3rem; border: 1px solid var(--border-color); border-radius: 4px; font-size: 0.85rem; font-family: var(--font-sans); color: var(--text-main);">
                            <option value="alpha" <?= $sort === 'alpha' ? 'selected' : '' ?>><?= msg('sort_alpha') ?></option>
                            <option value="amount_desc" <?= $sort === 'amount_desc' ? 'selected' : '' ?>><?= msg('sort_desc') ?></option>
                            <option value="amount_asc" <?= $sort === 'amount_asc' ? 'selected' : '' ?>><?= msg('sort_asc') ?></option>
                        </select>
                    </form>
                </div>
                <a href="advancedSearch.php" style="font-size: 0.85rem; color: var(--text-muted);"><?= msg('btn_reset') ?></a>
            </div>

            <?php if(empty($results)): ?>
                <p style="text-align:center; color: var(--text-muted);"><?= msg('adv_no_results') ?></p>
            <?php else: ?>
                <?php 
                $count = $offset + 1;
                // Render each pensioner card dynamically
                foreach($results as $row): 
                    $nom = htmlspecialchars($row['last_name'] ?? 'Inconnu');
                    $prenom = htmlspecialchars($row['first_name'] ?? '');
                    $montant = number_format($row['total_amount'] ?? 0, 0, ',', ' ') . ' L';
                    $titre = getJobTitle($row['jobs'] ?? null, $row['detailed_pensions'] ?? null);
                    $desc = getDescription($row['detailed_pensions'] ?? null, $row['identity_text'] ?? '');
                ?>
                <a href="pensionnaire.php?id=<?= $row['id'] ?>" class="result-card">
                    <div class="result-id"><?= sprintf('%02d', $count++) ?></div>
                    <div class="result-content">
                        <div class="result-top">
                            <div class="result-name"><strong><?= $nom ?></strong> <?= $prenom ?></div>
                            <div class="result-meta"><span class="result-amount"><?= $montant ?></span></div>
                        </div>
                        <div class="result-subtitle"><?= htmlspecialchars($titre) ?></div>
                        <div class="result-desc"><?= $desc ?></div>
                    </div>
                </a>
                <?php endforeach; ?>
                
                <!-- Sliding window pagination with direct page input -->
                <?php if ($totalPages > 1): ?>
                    <div class="pagination">
                        
                        <?php 
                        $startPage = max(1, $page - 1);
                        $endPage = min($totalPages, $page + 1);
                        
                        // Adjust window if on the first page
                        if ($page == 1 && $totalPages >= 3) {
                            $endPage = 3;
                        }
                        // Adjust window if on the last page
                        if ($page == $totalPages && $totalPages >= 3) {
                            $startPage = $totalPages - 2;
                        }

                        for($i = $startPage; $i <= $endPage; $i++): 
                        ?>
                            <a href="?page=<?=$i?><?=$urlParams?>" class="page-link <?=$i === $page ? 'active' : ''?>"><?=$i?></a>
                        <?php endfor; ?>
                        
                        <!-- Link to the last page (if not within the sliding window) -->
                        <?php if ($endPage < $totalPages): ?>
                            <?php if ($endPage < $totalPages - 1): ?>
                                <span style="display:flex; align-items:flex-end; padding:0 0.2rem; color:var(--text-muted)">...</span>
                            <?php endif; ?>
                            <a href="?page=<?=$totalPages?><?=$urlParams?>" class="page-link"><?=$totalPages?></a>
                        <?php endif; ?>
                        
                        <!-- Page number input for direct navigation (displayed if pages exceed window size) -->
                        <?php if ($totalPages > 3): ?>
                            <form action="" method="GET" class="pagination-form" style="margin-left: 0.5rem;">
                                <?php 
                                // Rebuild hidden inputs to maintain search criteria on pagination form submit
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

            <?php endif; ?>
        </section>
        <?php endif; ?>
    </main>
    <footer><a href="#"><?= msg('footer_legal') ?></a></footer>

    <!-- Client-side script to handle dynamic addition and removal of form rows -->
    <script>
        document.addEventListener('click', function(e) {
            if (e.target.classList.contains('add-btn')) {
                const row = e.target.closest('.adv-row');
                const newRow = row.cloneNode(true);
                newRow.querySelector('.adv-input').value = '';
                
                // Append remove button to new row if not present
                if (!newRow.querySelector('.remove-btn')) {
                    const removeBtn = document.createElement('button');
                    removeBtn.type = 'button';
                    removeBtn.className = 'adv-btn adv-btn-remove remove-btn';
                    removeBtn.textContent = '-';
                    newRow.appendChild(removeBtn);
                }
                document.getElementById('form-rows').appendChild(newRow);
            }
            if (e.target.classList.contains('remove-btn')) {
                e.target.closest('.adv-row').remove();
            }
        });
    </script>
</body>
</html>