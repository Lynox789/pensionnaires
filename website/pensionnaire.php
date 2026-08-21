<?php
// Load configuration and data model
require_once 'config.php';
require_once 'PensionnairesModel.php';

$id = $_GET['id'] ?? null;

// Validate ID parameter and redirect to error page if missing
if (!$id) {
    header("Location: error.php?key=err_missing_id");
    exit;
}

// Fetch pensioner data
$model = new PensionnairesModel();
$personne = $model->getPensionnaireById($id);

// Redirect to error page if pensioner is not found
if (!$personne) {
    header("Location: error.php?key=err_not_found");
    exit;
}

// Fetch related OpenData external links
$opendataLinks = $model->getOpendataLinks($personne['uid']);

// Prepare and format data for display
$nom = htmlspecialchars($personne['last_name'] ?? '');
$prenom = htmlspecialchars($personne['first_name'] ?? '');
$age = $personne['age'] ? $personne['age'] . ' ' . msg('age_years') : msg('age_unknown');
$montant = number_format($personne['total_amount'] ?? 0, 0, ',', ' ') . ' L';
$pensions = json_decode($personne['detailed_pensions'] ?? '[]', true);
$jobs = json_decode($personne['jobs'] ?? '[]', true);
?>
<!DOCTYPE html>
<html lang="<?= $currentLang ?>">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?= $nom ?> <?= $prenom ?> - Pensionnaires</title>
    <link rel="stylesheet" href="css/global.css">
    <link rel="stylesheet" href="css/pensionnaire.css">
</head>
<body>
    <header>
        <a href="index.php" class="logo">Pensionnaires</a>
        <nav>
            <a href="index.php"><?= msg('nav_search') ?></a>
            <a href="advancedSearch.php"><?= msg('nav_advanced') ?></a>
            <a href="sources.php"><?= msg('nav_sources') ?></a>
        </nav>
        
        <div class="lang-switcher">
            <?php 
            // Preserve URL parameters for language switching
            $queryParams = $_GET;
            $queryParams['lang'] = 'fr';
            $urlFr = '?' . http_build_query($queryParams);
            
            $queryParams['lang'] = 'en';
            $urlEn = '?' . http_build_query($queryParams);
            ?>
            <a href="<?= $urlFr ?>" class="<?= $currentLang === 'fr' ? 'active' : '' ?>">
                <img src="img/fr.png" alt="Français">
            </a>
            <a href="<?= $urlEn ?>" class="<?= $currentLang === 'en' ? 'active' : '' ?>">
                <img src="img/en.png" alt="English">
            </a>
        </div>
    </header>

    <main class="details-container">
        <a href="javascript:history.back()" class="back-link">← <?= msg('pen_back') ?></a>

        <div class="details-header">
            <div class="details-title">
                <h1><strong><?= $nom ?></strong> <?= $prenom ?></h1>
                <div class="meta-tags">
                    <span><?= $age ?></span>
                    <?php if($personne['birth_year']): ?>
                        <span><?= msg('pen_born') ?> <?= htmlspecialchars($personne['birth_year']) ?></span>
                    <?php endif; ?>
                </div>
            </div>
            <div class="details-amount">
                <span><?= msg('pen_total_amount') ?></span>
                <strong><?= $montant ?></strong>
            </div>
        </div>

        <div class="details-grid">
            <div class="main-column">
                
                <!-- Display list of jobs and roles if available -->
                <?php if(!empty($jobs) && is_array($jobs)): ?>
                <section class="detail-section">
                    <h2><?= msg('pen_jobs') ?></h2>
                    <div class="pension-box" style="padding: 1rem 1.5rem;">
                        <ul style="list-style-type: disc; margin-left: 1.5rem; color: var(--text-main); font-size: 0.95rem;">
                            <?php foreach($jobs as $job): ?>
                                <?php if(!empty($job['text'])): ?>
                                    <li style="margin-bottom: 0.5rem;"><?= htmlspecialchars(ucfirst($job['text'])) ?></li>
                                <?php endif; ?>
                            <?php endforeach; ?>
                        </ul>
                    </div>
                </section>
                <?php endif; ?>

                <!-- Loop through and display detailed pensions -->
                <section class="detail-section">
                    <h2><?= msg('pen_details') ?></h2>
                    <?php if(empty($pensions)): ?>
                        <p class="text-muted"><?= msg('pen_no_details') ?></p>
                    <?php else: ?>
                        <?php foreach($pensions as $p): ?>
                            <div class="pension-box">
                                <div class="pension-top">
                                    <span class="pension-type"><?= htmlspecialchars(ucfirst($p['type'] ?? 'Pension')) ?></span>
                                    <span class="pension-amount"><?= number_format($p['amount'] ?? 0, 0, ',', ' ') ?> L</span>
                                </div>
                                <?php if(isset($p['department'])): ?>
                                    <div class="pension-dept"><?= msg('pen_dept') ?> <?= htmlspecialchars($p['department']) ?></div>
                                <?php endif; ?>
                                <div class="pension-text">
                                    "<?= htmlspecialchars($p['text'] ?? '') ?>"
                                </div>
                            </div>
                        <?php endforeach; ?>
                    <?php endif; ?>
                </section>
            </div>

            <div class="side-column">
                <!-- Display external authority links with verification status -->
                <section class="detail-section">
                    <h2><?= msg('pen_ext_links') ?></h2>
                    <?php if(empty($opendataLinks)): ?>
                        <div class="opendata-box text-muted" style="background: white; padding: 1.5rem; border: 1px solid var(--border-color); border-radius: 6px;">
                            <?= msg('pen_no_links') ?>
                        </div>
                    <?php else: ?>
                        <ul class="opendata-list">
                            <?php foreach($opendataLinks as $link): ?>
                                <li style="flex-direction: row; flex-wrap: wrap; align-items: center; justify-content: space-between;">
                                    <div style="display: flex; flex-direction: column; gap: 0.3rem;">
                                        <span class="base-name"><?= htmlspecialchars(strtoupper($link['base'])) ?></span>
                                        <a href="<?= htmlspecialchars($link['url']) ?>" target="_blank" class="base-link" style="font-family: var(--font-sans); font-size: 0.85rem;">
                                            <?= msg('pen_consult_source') ?> ↗
                                        </a>
                                    </div>
                                    <div>
                                        <?php if(!empty($link['validation_date'])): ?>
                                            <span style="display: inline-block; padding: 0.2rem 0.5rem; background-color: var(--tag-m); color: white; border-radius: 4px; font-size: 0.7rem; font-weight: bold;">
                                                <?= msg('pen_verified') ?>
                                            </span>
                                        <?php else: ?>
                                            <span style="display: inline-block; padding: 0.2rem 0.5rem; background-color: #d1d0c9; color: var(--text-main); border-radius: 4px; font-size: 0.7rem; font-weight: bold;">
                                                <?= msg('pen_not_verified') ?>
                                            </span>
                                        <?php endif; ?>
                                    </div>
                                </li>
                            <?php endforeach; ?>
                        </ul>
                    <?php endif; ?>
                </section>
            </div>
        </div>
    </main>

    <footer><a href="#"><?= msg('footer_legal') ?></a></footer>
</body>
</html>