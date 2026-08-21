<?php
//Initialize session to store user preferences like language selection
session_start();
require_once 'Database.php';

//Handle language selection and update session data
if (isset($_GET['lang']) && in_array($_GET['lang'], ['fr', 'en'])) {
    $_SESSION['lang'] = $_GET['lang'];
}

//Default to French if no language is currently set
$currentLang = $_SESSION['lang'] ?? 'fr';

//Initialize database connection to load translations
$db = new Database();
$pdo = $db->getConnection();

//Optimize query by fetching translations only for the active language
$sql = "SELECT msg_key, content_{$currentLang} as content FROM translations";
$stmt = $pdo->query($sql);

//Populate an associative array with the translation dictionary
$textes = [];
while ($row = $stmt->fetch()) {
    $textes[$row['msg_key']] = $row['content'];
}

//Helper function to output localized strings safely
if (!function_exists('msg')) {
    function msg($key) {
        global $textes;
        // Return the translated string securely, or fallback to the raw key if missing
        return htmlspecialchars($textes[$key] ?? "[{$key}]");
    }
}
?>