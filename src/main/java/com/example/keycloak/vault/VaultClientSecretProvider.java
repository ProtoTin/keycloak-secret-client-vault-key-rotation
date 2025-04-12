package com.example.keycloak.vault;

import org.keycloak.models.ClientModel;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.RealmModel;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class VaultClientSecretProvider implements ClientSecretManager {
    private static final Logger logger = LoggerFactory.getLogger(VaultClientSecretProvider.class);
    private final VaultClient vaultClient;
    private final KeycloakSession session;

    public VaultClientSecretProvider(KeycloakSession session) {
        this.session = session;
        this.vaultClient = new VaultClient();
    }

    @Override
    public String generateSecret(RealmModel realm, ClientModel client) {
        String secret = generateRandomSecret();
        vaultClient.setClientSecret(client.getClientId(), secret);
        return secret;
    }

    @Override
    public String getClientSecret(RealmModel realm, ClientModel client) {
        try {
            return vaultClient.getClientSecret(client.getClientId());
        } catch (Exception e) {
            logger.warn("Failed to get client secret from Vault, generating new one", e);
            return generateSecret(realm, client);
        }
    }

    private String generateRandomSecret() {
        // Generate a secure random secret
        byte[] bytes = new byte[32];
        new java.security.SecureRandom().nextBytes(bytes);
        return java.util.Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }
}