<?php
// Load global configuration and translation helpers
require_once 'config.php';
?>
<!DOCTYPE html>
<html lang="<?= $currentLang ?>">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?= msg('src_title') ?></title>
    <link rel="stylesheet" href="css/global.css">
    <link rel="stylesheet" href="css/sources.css">
</head>
<body>

    <header>
        <a href="index.php" class="logo">Pensionnaires</a>
        <nav>
            <a href="index.php"><?= msg('nav_search') ?></a>
            <a href="advancedSearch.php"><?= msg('nav_advanced') ?></a>
            <a href="sources.php" class="active"><?= msg('nav_sources') ?></a>
        </nav>
        
        <div class="lang-switcher">
            <?php 
            // Preserve existing query parameters when switching languages
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

    <div class="sources-hero">
        <?= msg('src_hero') ?>
    </div>

    <main class="sources-container">
        <h1><?= msg('src_h1') ?></h1>
        <p><?= msg('src_subtitle') ?></p>

        <section class="source-section">
            <h3><?= msg('src_ref_title') ?></h3>
            <div class="source-box">
                <!-- Empty container reserved for mockup layout consistency -->
                <br>
            </div>
        </section>

        <section class="source-section">
            <h3><?= msg('src_classes_title') ?> <span><?= msg('src_classes_span') ?></span></h3>
            <ul class="source-list">
                <li>Cl. I</li>
                <li>Cl. II</li>
                <li>Cl. III</li>
                <li>Cl. IV</li>
                <li>Cl. V</li>
                <li>Cl. VI</li>
                <li>Cl. VII</li>
            </ul>
        </section>

        <section class="source-section">
            <h3><?= msg('src_method_title') ?></h3>
            <div class="source-box" style="background-color: #fcfcfc;">
                <!-- Placeholder space for future methodology content -->
                <br><br><br>
            </div>
        </section>
    </main>

    <footer>
        <a href="#"><?= msg('footer_legal') ?></a>
    </footer>

</body>
</html>