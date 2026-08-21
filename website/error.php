<?php
// Load global configuration and translation helpers
require_once 'config.php';

// Determine the error message to display using a translation key or a fallback message
if (isset($_GET['key'])) {
    $errorMessage = msg($_GET['key']);
} else {
    $errorMessage = $_GET['msg'] ?? msg('err_default_msg');
}
?>
<!DOCTYPE html>
<html lang="<?= $currentLang ?>">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?= msg('err_title') ?></title>
    <link rel="stylesheet" href="css/global.css">
    <link rel="stylesheet" href="css/error.css">
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
        <!-- Display the localized error message and return link -->
        <div class="error-container">
            <h1><?= msg('err_h1') ?></h1>
            <p><?= htmlspecialchars($errorMessage) ?></p>
            <a href="index.php" class="btn-back"><?= msg('err_btn_back') ?></a>
        </div>
    </main>

    <footer>
        <a href="#"><?= msg('footer_legal') ?></a>
    </footer>
</body>
</html>