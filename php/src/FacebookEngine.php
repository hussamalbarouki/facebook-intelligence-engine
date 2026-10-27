<?php
declare(strict_types=1);
/**
 * Server-side PHP 8.1+ SDK for Facebook Intelligence Engine.
 * Never send API_KEY or Facebook cookies to browser JavaScript.
 */
final class FacebookEngine
{
    public function __construct(
        private readonly string $baseUrl,
        private readonly string $apiKey,
        private readonly int $timeoutSeconds = 20
    ) {
        if (!preg_match('~^https://[^/]+$~i', rtrim($baseUrl, '/'))) {
            throw new InvalidArgumentException('API endpoint must be an HTTPS origin without path');
        }
        if (strlen($apiKey) < 32) {
            throw new InvalidArgumentException('API key must be at least 32 characters');
        }
    }

    private function call(string $method, string $path, ?array $json = null): array
    {
        $ch = curl_init(rtrim($this->baseUrl, '/') . $path);
        if ($ch === false) { throw new RuntimeException('Could not initialize cURL'); }
        $headers = ['Accept: application/json', 'X-API-Key: ' . $this->apiKey];
        if ($json !== null) { $headers[] = 'Content-Type: application/json'; }
        $options = [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_CUSTOMREQUEST => $method,
            CURLOPT_HTTPHEADER => $headers,
            CURLOPT_CONNECTTIMEOUT => 6,
            CURLOPT_TIMEOUT => $this->timeoutSeconds,
            CURLOPT_FOLLOWLOCATION => false,
            CURLOPT_SSL_VERIFYPEER => true,
            CURLOPT_SSL_VERIFYHOST => 2,
        ];
        if ($json !== null) {
            $options[CURLOPT_POSTFIELDS] = json_encode($json, JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE);
        }
        curl_setopt_array($ch, $options);
        $raw = curl_exec($ch);
        $status = curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
        $curlError = curl_error($ch);
        curl_close($ch);
        if ($raw === false) {
            throw new RuntimeException('Engine connection error: ' . $curlError);
        }
        $payload = json_decode($raw, true);
        if (!is_array($payload)) { throw new RuntimeException('Engine returned invalid JSON, HTTP ' . $status); }
        if ($status >= 400) {
            $detail = is_string($payload['detail'] ?? null) ? $payload['detail'] : 'Request failed';
            throw new RuntimeException('Engine HTTP ' . $status . ': ' . $detail, (int)$status);
        }
        return $payload;
    }

    public function health(): array { return $this->call('GET', '/healthz'); }
    public function status(): array { return $this->call('GET', '/v1/status'); }
    public function capabilities(): array { return $this->call('GET', '/v1/capabilities'); }
    public function settings(): array { return $this->call('GET', '/v1/settings'); }
    public function updateSettings(array $settings): array { return $this->call('PATCH', '/v1/settings', $settings); }

    /** Accept name-value map (c_user, xs, ...) or a browser-exported cookies array. */
    public function setCookies(array $cookies): array { return $this->call('PUT', '/v1/facebook/cookies', ['cookies' => $cookies]); }
    public function cookiesStatus(): array { return $this->call('GET', '/v1/facebook/cookies'); }
    public function removeCookies(): array { return $this->call('DELETE', '/v1/facebook/cookies'); }

    public function startJob(string $postUrl, ?int $commentsLimit = null, ?int $reactorsLimit = null, ?string $clientJobId = null): array
    {
        $data = ['url' => $postUrl];
        if ($commentsLimit !== null) { $data['comments_limit'] = $commentsLimit; }
        if ($reactorsLimit !== null) { $data['reactors_limit'] = $reactorsLimit; }
        if ($clientJobId !== null) { $data['client_job_id'] = $clientJobId; }
        return $this->call('POST', '/v1/jobs', $data);
    }
    public function listJobs(?string $status = null, int $limit = 30, int $offset = 0): array
    {
        $params = ['limit' => $limit, 'offset' => $offset];
        if ($status !== null) { $params['status'] = $status; }
        return $this->call('GET', '/v1/jobs?' . http_build_query($params));
    }
    public function getJob(string $jobId): array { return $this->call('GET', '/v1/jobs/' . rawurlencode($jobId)); }
    public function retryJob(string $jobId): array { return $this->call('POST', '/v1/jobs/' . rawurlencode($jobId) . '/retry'); }
    public function cancelJob(string $jobId): array { return $this->call('POST', '/v1/jobs/' . rawurlencode($jobId) . '/cancel'); }
    public function getResult(string $jobId, int $commentsOffset = 0, int $reactorsOffset = 0, int $limit = 100): array
    {
        return $this->call('GET', '/v1/jobs/' . rawurlencode($jobId) . '/result?' . http_build_query([
            'comments_offset'=>$commentsOffset, 'reactors_offset'=>$reactorsOffset, 'limit'=>$limit,
        ]));
    }
    public function metrics(): array { return $this->call('GET', '/v1/metrics'); }
    public function events(int $limit = 30): array { return $this->call('GET', '/v1/events?limit=' . $limit); }
}