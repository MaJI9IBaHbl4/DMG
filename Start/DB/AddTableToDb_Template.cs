// Dobavlenie novoi tablicy
1. Модель
2. Конфигурация
3. DbSet
4. DTO (Create, Update, Response)
5. Эндпойнты (GET all, GET by id, POST, PUT, DELETE)
6. Сборка
7. Миграция

================================================================
== 1. Добавляешь модель
================================================================
namespace MyBackend.Models;

public class Machine
{
    public int Id { get; set; }
    public string Name { get; set; } = null!;
    public DateTime CreatedAt { get; set; }
}



================================================================
== 2. Добавляешь конфигурацию (если используешь Configurations)
================================================================
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using MyBackend.Models;

namespace MyBackend.Data.Configurations;

public sealed class MachineConfiguration : IEntityTypeConfiguration<Machine>
{
    public void Configure(EntityTypeBuilder<Machine> b)
    {
        b.ToTable("Machines");

        b.HasKey(x => x.Id);

        b.Property(x => x.Name)
            .HasMaxLength(200)
            .IsRequired();

        b.Property(x => x.CreatedAt)
            .HasDefaultValueSql("SYSUTCDATETIME()")
            .ValueGeneratedOnAdd();
    }
}



================================================================
== 3. Добавляешь DbSet в контекст
================================================================
В AppDb:

public DbSet<Machine> Machines => Set<Machine>();



================================================================
== 4. DTO (Data Transfer Objects)
================================================================
namespace MyBackend.Models;

// DTO для создания
public record MachineCreate(string Name);

// DTO для ответа
public record MachineDto(int Id, string Name, DateTime CreatedAt);

// DTO для обновления
public record MachineUpdate(string? Name);



================================================================
== 5. Эндпойнты
================================================================
using Microsoft.EntityFrameworkCore;
using MyBackend.Data;
using MyBackend.Models;

namespace MyBackend.Endpoints.Api.V1;

public sealed class MachinesEndpoints : IEndpoint
{
    public void MapEndpoints(IEndpointRouteBuilder app)
    {
        var v1 = app.MapGroup("/api/v1");
        var machines = v1.MapGroup("/machines").WithTags("Machines V1");

        // ===============================================================================
        // GET - Gauti visas machines
        // ===============================================================================
        machines.MapGet("/", async (AppDb db) =>
                Results.Ok(await db.Machines
                    .OrderByDescending(m => m.Id)
                    .Select(m => new MachineDto(m.Id, m.Name, m.CreatedAt))
                    .ToListAsync()))
        .WithName("GetMachines")
        .WithOpenApi(op => { 
            op.Summary = "Get all machines"; 
            return op; 
        });

        // ===============================================================================
        // GET - Gauti viena machine pagal ID
        // ===============================================================================
        machines.MapGet("/{id:int}", async (int id, AppDb db) =>
        {
            var m = await db.Machines.FindAsync(id);
            return m is null 
                ? Results.NotFound() 
                : Results.Ok(new MachineDto(m.Id, m.Name, m.CreatedAt));
        })
        .WithName("GetMachineById")
        .WithOpenApi(op => { 
            op.Summary = "Get machine by id"; 
            return op; 
        });


        // ===============================================================================
        // POST - Sukurti machine
        // ===============================================================================
        machines.MapPost("/", async (MachineCreate dto, AppDb db) =>
        {
            if (string.IsNullOrWhiteSpace(dto.Name))
                return Results.ValidationProblem(new Dictionary<string, string[]>
                { ["name"] = new[] { "Name is required." } });

            var m = new Machine
            {
                Name = dto.Name.Trim(),
                CreatedAt = DateTime.UtcNow
            };

            db.Add(m);
            await db.SaveChangesAsync();

            return Results.Created($"/api/v1/machines/{m.Id}", 
                new MachineDto(m.Id, m.Name, m.CreatedAt));
        })
        .WithName("CreateMachine")
        .WithOpenApi(op => { 
            op.Summary = "Create machine"; 
            return op; 
        })
        .Accepts<MachineCreate>("application/json")
        .Produces<MachineDto>(StatusCodes.Status201Created)
        .Produces(StatusCodes.Status400BadRequest);


        // ===============================================================================
        // PUT - Atnaujinti machine
        // ===============================================================================
        machines.MapPut("/{id:int}", async (int id, MachineUpdate dto, AppDb db) =>
        {
            var m = await db.Machines.FindAsync(id);
            if (m is null) 
                return Results.NotFound();

            if (!string.IsNullOrWhiteSpace(dto.Name))
                m.Name = dto.Name.Trim();

            await db.SaveChangesAsync();

            return Results.Ok(new MachineDto(m.Id, m.Name, m.CreatedAt));
        })
        .WithName("UpdateMachine")
        .WithOpenApi(op => { 
            op.Summary = "Update machine"; 
            return op; 
        })
        .Accepts<MachineUpdate>("application/json")
        .Produces<MachineDto>(StatusCodes.Status200OK)
        .Produces(StatusCodes.Status404NotFound);


        // ===============================================================================
        // DELETE - Ištrinti machine
        // ===============================================================================
        machines.MapDelete("/{id:int}", async (int id, AppDb db) =>
        {
            var m = await db.Machines.FindAsync(id);
            if (m is null) 
                return Results.NotFound();

            db.Remove(m);
            await db.SaveChangesAsync();

            return Results.NoContent();
        })
        .WithName("DeleteMachine")
        .WithOpenApi(op => { 
            op.Summary = "Delete machine"; 
            return op; 
        })
        .Produces(StatusCodes.Status204NoContent)
        .Produces(StatusCodes.Status404NotFound);
    }
}



================================================================
== 6. Пересобираем проект
================================================================
Ctrl + Shift + B



================================================================
== 7. Генерируем и применяем миграцию
================================================================
Add-Migration AddMachinesTable
Update-Database
