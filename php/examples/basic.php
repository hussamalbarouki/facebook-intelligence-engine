<?php
declare(strict_types=1);
require __DIR__ . '/../src/FacebookEngine.php';

// Configure in private cPanel environment, never commit actual values to GitHub.
$engine = new FacebookEngine(getenv('FB_ENGINE_URL'), getenv('FB_ENGINE_KEY'));

// ADMIN: update Facebook session from your protected PHP control panel.
// $engine->setCookies(['c_user' => '...','xs' => '...']);

// For a new post, submit async job and store job_id in your cPanel database.
$job = $engine->startJob('https://www.facebook.com/EXAMPLE/posts/123456789', 50, 50, 'site-task-1001');
print_r($job);

// From a later PHP request (not long-polling), read status:
// $status = $engine->getJob($job['job_id']);
// if ($status['status'] === 'completed') $page = $engine->getResult($job['job_id']);