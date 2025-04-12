package com.example.keycloak.vault;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Base64;
import java.util.Map;
import java.util.logging.Logger;

public class VaultClient {
    private static final Logger logger = Logger.getLogger(VaultClient.class.getName());
    private final String vaultAddr;
    private final String vaultToken;
    private final HttpClient httpClient;

    public VaultClient() {
        this.vaultAddr = System.getenv("VAULT_ADDR");
        this.vaultToken = System.getenv("VAULT_TOKEN");

        if (vaultAddr == null || vaultToken == null) {
            throw new IllegalStateException("VAULT_ADDR and VAULT_TOKEN environment variables must be set");
        }

        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();
    }

    public String getClientSecret(String clientId) {
        try {
            String path = String.format("%s/v1/kv/data/keycloak/clients/%s", vaultAddr, clientId);
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(path))
                    .header("X-Vault-Token", vaultToken)
                    .GET()
                    .build();

            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() == 200) {
                logger.info("Successfully retrieved client secret from Vault");
                return response.body();
            } else {
                logger.warning("Failed to get client secret from Vault. Status: " + response.statusCode());
                return null;
            }
        } catch (IOException | InterruptedException e) {
            logger.severe("Error getting client secret from Vault: " + e.getMessage());
            return null;
        }
    }

    public boolean setClientSecret(String clientId, String secret) {
        try {
            String path = String.format("%s/v1/kv/data/keycloak/clients/%s", vaultAddr, clientId);
            String jsonBody = String.format("{\"data\": {\"value\": \"%s\"}}", secret);

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(path))
                    .header("X-Vault-Token", vaultToken)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(jsonBody))
                    .build();

            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() == 200 || response.statusCode() == 204) {
                logger.info("Successfully stored client secret in Vault");
                return true;
            } else {
                logger.warning("Failed to store client secret in Vault. Status: " + response.statusCode()
                        + ", Response: " + response.body());
                return false;
            }
        } catch (IOException | InterruptedException e) {
            logger.severe("Error storing client secret in Vault: " + e.getMessage());
            return false;
        }
    }
}