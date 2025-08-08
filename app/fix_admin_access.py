# fix_admin_access.py
from db import buscar_usuario, salvar_usuario

# Garantir acesso dos admins existentes
admins = [
    "lins",
    "linsalefe", 
    "alefelins",
    "ba8254e3-b75b-4522-97a8-aeb977a02126"
]

for admin_user in admins:
    user = buscar_usuario(admin_user)
    if user:
        user["has_access"] = True
        user["is_admin"] = True
        salvar_usuario(user)
        print(f"✅ Admin {admin_user} atualizado")
    else:
        print(f"❌ Admin {admin_user} não encontrado")

print("✅ Admins atualizados com sucesso!")