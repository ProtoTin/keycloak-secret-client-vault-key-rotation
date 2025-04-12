package com.example.keycloak.vault;

import org.keycloak.Config;
import org.keycloak.models.KeycloakSession;
import org.keycloak.models.KeycloakSessionFactory;

public class VaultClientSecretProviderFactory implements ClientSecretManagerFactory {
    @Override
    public ClientSecretManager create(KeycloakSession session) {
        return new VaultClientSecretProvider(session);
    }

    @Override
    public void init(Config.Scope config) {
        // No initialization needed
    }

    @Override
    public void postInit(KeycloakSessionFactory factory) {
        // No post-initialization needed
    }

    @Override
    public void close() {
        // No cleanup needed
    }

    @Override
    public String getId() {
        return "vault";
    }
}