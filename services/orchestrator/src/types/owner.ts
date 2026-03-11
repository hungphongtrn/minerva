export interface OwnerPrincipal {
  tenantId: string;
  subjectId: string;
}

export function ownerKeyFromPrincipal(owner: OwnerPrincipal): string {
  if (owner.tenantId === 'legacy') {
    return owner.subjectId;
  }

  return `${encodeURIComponent(owner.tenantId)}:${encodeURIComponent(owner.subjectId)}`;
}

export function sameOwnerPrincipal(left: OwnerPrincipal, right: OwnerPrincipal): boolean {
  return left.tenantId === right.tenantId && left.subjectId === right.subjectId;
}

export function legacyOwnerPrincipalFromUserId(userId: string): OwnerPrincipal {
  return {
    tenantId: 'legacy',
    subjectId: userId,
  };
}
