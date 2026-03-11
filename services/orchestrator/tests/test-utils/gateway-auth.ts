export interface GatewayAuthHeadersInput {
  tenantId?: string;
  subjectId?: string;
  proof?: string;
}

export function createGatewayAuthHeaders(
  input: GatewayAuthHeadersInput = {}
): Record<string, string> {
  return {
    'x-minerva-gateway-proof': input.proof ?? process.env.GATEWAY_PROOF_SECRET ?? 'test-gateway-proof',
    'x-minerva-tenant-id': input.tenantId ?? 'tenant-1',
    'x-minerva-subject-id': input.subjectId ?? 'user-1',
  };
}
